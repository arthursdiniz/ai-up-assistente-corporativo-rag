"""Private PostgreSQL cluster for fresh Windows installations."""
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import socket
import stat
from tempfile import mkdtemp
from zipfile import ZipFile

from scripts.windows_bootstrap import (SetupError, command, consent, download, file_sha256,
                                       reject_link, require_space, say, write_text)


PG_URL = "https://get.enterprisedb.com/postgresql/postgresql-18.7-1-windows-x64-binaries.zip"
PG_SHA256 = "ead0bbc27fb678fa24dcf86b738981323042abd073c744103bf7f3aed23f9a33"
APP_USER = "aiup_app"
ADMIN_USER = "aiup_bootstrap"
DB_NAME = "ai_up"
PG_TOOLS = ("postgres.exe", "initdb.exe", "pg_ctl.exe")
PRIVATE_PORTS = range(55432, 55452)
TOKEN = re.compile(r"[A-Za-z0-9_-]{40,100}\Z")
DEVICES = re.compile(r"(?i)(?:CON|PRN|AUX|NUL|COM[1-9¹²³]|LPT[1-9¹²³])(?:\.|$)")


def discover_bin(home):
    candidates = [home / "postgresql" / "bin"]
    path = shutil.which("pg_ctl.exe")
    if path:
        candidates.append(Path(path).parent)
    program_files = os.environ.get("ProgramFiles")
    if program_files:
        installs = Path(program_files) / "PostgreSQL"
        candidates.extend(installs / str(major) / "bin" for major in (18, 17, 16))
    return next((directory for directory in candidates if all((directory / name).is_file() for name in PG_TOOLS)), None)


def install_portable(home):
    require_space(home, 3)
    archive = home / "postgresql-18.7.zip"
    reject_link(archive)
    if not archive.is_file() or file_sha256(archive) != PG_SHA256:
        if not consent("Baixar PostgreSQL 18.7 oficial da EDB (~390 MB) e preparar um cluster privado, sem instalar um serviço global?"):
            raise SetupError("PostgreSQL é obrigatório. Instale os binários oficiais ou configure um servidor existente.")
        say("Baixando e verificando o arquivo PostgreSQL da EDB...")
        download(PG_URL, PG_SHA256, archive, 420 * 1024**2)
    stage = Path(mkdtemp(prefix="postgresql-install-", dir=home))
    try:
        with ZipFile(archive) as package:
            package.extractall(stage, members=portable_members(package))
        directory = stage / "pgsql"
        if not all((directory / "bin" / name).is_file() for name in PG_TOOLS):
            raise SetupError("O pacote PostgreSQL não contém todos os executáveis necessários.")
        directory.rename(home / "postgresql")
        archive.unlink(missing_ok=True)
        return home / "postgresql" / "bin"
    finally:
        shutil.rmtree(stage, ignore_errors=True)


def portable_members(package):
    members = []
    names = set()
    total = 0
    for item in package.infolist():
        # Inspect the original name, including embedded NUL, before zipfile normalizes it.
        parts = item.orig_filename.rstrip("/").split("/")
        if len(parts) < 2 or parts[0] != "pgsql" or parts[1] not in {"bin", "lib", "share"}:
            continue
        key = "/".join(parts).casefold()
        if (key in names or stat.S_ISLNK(item.external_attr >> 16)
                or any(not part or part.endswith((".", " ")) or DEVICES.match(part)
                       or any(ord(char) < 32 or char in '<>:"\\|?*' for char in part) for part in parts)):
            raise SetupError("O pacote PostgreSQL contém um caminho inesperado.")
        names.add(key)
        total += item.file_size
        if total > 2 * 1024**3:
            raise SetupError("O pacote PostgreSQL ultrapassa o tamanho esperado após extração.")
        members.append(item)
    return members


def port_available(port):
    with socket.socket() as probe:
        if os.name == "nt":
            probe.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        try:
            probe.bind(("127.0.0.1", port))
        except OSError:
            return False
    return True


def choose_port(excluding=None):
    for port in PRIVATE_PORTS:
        if port != excluding and port_available(port):
            return port
    raise SetupError("Nenhuma porta local livre para o PostgreSQL privado (55432 a 55451).")


def initialize(bin_dir, cluster, password):
    stage = Path(mkdtemp(prefix="cluster-init-", dir=cluster.parent))
    password_file = stage / "password"
    try:
        write_text(password_file, password + "\n")
        data = stage / "data"
        result = command([bin_dir / "initdb.exe", "-D", data, "-U", ADMIN_USER, "--auth=scram-sha-256",
                          "--pwfile", password_file, "--encoding=UTF8", "--locale=C"], timeout=90)
        if result.returncode:
            raise SetupError(f"O initdb falhou (código {result.returncode}). Confira runtime do Visual C++, espaço e permissões.")
        data.rename(cluster)
    finally:
        shutil.rmtree(stage, ignore_errors=True)


def status(bin_dir, cluster):
    code = command([bin_dir / "pg_ctl.exe", "status", "-D", cluster]).returncode
    if code not in (0, 3):
        raise SetupError(f"O pg_ctl não conseguiu consultar o cluster (código {code}). Confira a pasta e suas permissões.")
    return code == 0


def start(bin_dir, cluster, port):
    pg_ctl = bin_dir / "pg_ctl.exe"
    say(f"Iniciando o PostgreSQL privado em 127.0.0.1:{port}...")
    result = command([pg_ctl, "start", "-D", cluster, "-l", cluster.parent / "postgresql.log",
                      "-o", f"-h 127.0.0.1 -p {port}", "-w", "-t", "45"], timeout=55, quiet=True)
    if result.returncode:
        raise SetupError("O PostgreSQL privado não iniciou. Confira postgresql.log, a porta, o runtime do Visual C++ e o antivírus.")


def provision_role(cluster, port, state):
    import psycopg
    from psycopg import sql

    with psycopg.connect(host="127.0.0.1", port=port, user=ADMIN_USER, password=state["admin"],
                         dbname="postgres", connect_timeout=5, autocommit=True) as connection:
        directory = connection.execute("SHOW data_directory").fetchone()[0]
        if Path(directory).resolve() != cluster.resolve():
            raise SetupError("A porta do PostgreSQL privado respondeu com outro diretório de dados.")
        connection.execute("SET log_statement = 'none'")
        connection.execute("SET log_min_error_statement = 'panic'")
        if not connection.execute("SELECT 1 FROM pg_roles WHERE rolname=%s", (APP_USER,)).fetchone():
            connection.execute(sql.SQL("CREATE ROLE {} LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE PASSWORD {}").format(
                sql.Identifier(APP_USER), sql.Literal(state["password"])))
        if not connection.execute("SELECT 1 FROM pg_database WHERE datname=%s", (DB_NAME,)).fetchone():
            connection.execute(sql.SQL("CREATE DATABASE {} OWNER {}").format(sql.Identifier(DB_NAME), sql.Identifier(APP_USER)))


def read_state(path):
    reject_link(path)
    try:
        state = json.loads(path.read_text(encoding="utf-8"))
        if (not isinstance(state, dict) or not isinstance(state.get("bin"), str)
                or not Path(state["bin"]).is_absolute() or type(state.get("port")) is not int
                or state["port"] not in PRIVATE_PORTS
                or any(not isinstance(state.get(key), str) or not TOKEN.fullmatch(state[key])
                       for key in ("password", "admin") if key != "admin" or key in state)):
            raise ValueError
    except (OSError, ValueError) as exc:
        raise SetupError("O registro database.json do PostgreSQL privado está ilegível. Restaure uma cópia dessa configuração.") from exc
    return state


def prepare_database(home, *, allow_port_change=True):
    import psycopg

    cluster = home / "cluster"
    state_file = home / "database.json"
    reject_link(cluster)
    reject_link(state_file)
    if state_file.exists():
        state = read_state(state_file)
        bin_dir = Path(state["bin"])
        if not all((bin_dir / name).is_file() for name in PG_TOOLS):
            raise SetupError("Os binários do PostgreSQL privado não estão disponíveis. Reponha a mesma versão; o cluster foi preservado.")
    else:
        if cluster.exists():
            raise SetupError("Já existe um cluster sem registro de instalação. Recupere a configuração anterior antes de tentar novamente.")
        bin_dir = discover_bin(home) or install_portable(home)
        state = {"bin": str(bin_dir), "port": choose_port(), "admin": secrets.token_urlsafe(36),
                 "password": secrets.token_urlsafe(36)}
        write_text(state_file, json.dumps(state))
    if not (cluster / "PG_VERSION").is_file():
        if cluster.exists() or "admin" not in state:
            raise SetupError("O cluster PostgreSQL está incompleto ou ausente. Restaure uma cópia antes de continuar.")
        initialize(bin_dir, cluster, state["admin"])
    port = state["port"]
    if not status(bin_dir, cluster):
        if not port_available(port):
            if not allow_port_change:
                raise SetupError(f"A porta {port} do banco está ocupada. Libere a porta ou revise a conexão configurada.")
            port = choose_port(excluding=port)
            state["port"] = port
            write_text(state_file, json.dumps(state), replace=True)
            say(f"Porta anterior ocupada. O PostgreSQL privado usará a porta {port} com o mesmo cluster.")
        start(bin_dir, cluster, port)
    credentials = dict(host="127.0.0.1", port=port, user=APP_USER, password=state["password"], dbname=DB_NAME)
    try:
        if "admin" in state:
            provision_role(cluster, port, state)
        with psycopg.connect(**credentials, connect_timeout=5) as connection:
            connection.execute("SELECT 1")
    except psycopg.Error as exc:
        raise SetupError(f"Falha ao validar o banco privado ({type(exc).__name__}). Os dados existentes foram mantidos.") from exc
    if "admin" in state:
        del state["admin"]
        write_text(state_file, json.dumps(state), replace=True)
    return f"postgresql+psycopg://{APP_USER}:{state['password']}@127.0.0.1:{port}/{DB_NAME}"
