"""Private PostgreSQL cluster for fresh Windows installations."""
import json
import os
from pathlib import Path, PurePosixPath
import secrets
import shutil
import socket
from tempfile import mkdtemp
from zipfile import ZipFile

from scripts.windows_bootstrap import SetupError, command, consent, download, require_space, say, write_text


PG_URL = "https://get.enterprisedb.com/postgresql/postgresql-18.7-1-windows-x64-binaries.zip"
PG_SHA256 = "ead0bbc27fb678fa24dcf86b738981323042abd073c744103bf7f3aed23f9a33"
APP_USER = "aiup_app"
ADMIN_USER = "aiup_bootstrap"
DB_NAME = "ai_up"
PG_TOOLS = ("postgres.exe", "initdb.exe", "pg_ctl.exe")


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
    if not consent("Baixar PostgreSQL 18.7 oficial da EDB (~390 MB) e preparar um cluster privado, sem instalar um serviço global?"):
        raise SetupError("PostgreSQL é obrigatório. Instale os binários oficiais ou configure um servidor existente.")
    require_space(home, 3)
    stage = Path(mkdtemp(prefix="postgresql-install-", dir=home))
    archive = stage / "postgresql.zip"
    say("Baixando e verificando o arquivo PostgreSQL da EDB...")
    try:
        download(PG_URL, PG_SHA256, archive, 420 * 1024**2)
        with ZipFile(archive) as package:
            # Keep server, tools and libraries, excluding optional pgAdmin/StackBuilder assets.
            for item in package.infolist():
                parts = PurePosixPath(item.filename).parts
                if len(parts) < 2 or parts[0] != "pgsql" or parts[1] not in {"bin", "lib", "share"}:
                    continue
                if any(part == ".." or "\\" in part or ":" in part for part in parts):
                    raise SetupError("O pacote PostgreSQL contém um caminho inesperado.")
                package.extract(item, stage)
        directory = stage / "pgsql"
        if not all((directory / "bin" / name).is_file() for name in PG_TOOLS):
            raise SetupError("O pacote PostgreSQL não contém todos os executáveis necessários.")
        directory.rename(home / "postgresql")
        return home / "postgresql" / "bin"
    finally:
        shutil.rmtree(stage, ignore_errors=True)


def choose_port():
    for port in range(55432, 55452):
        with socket.socket() as probe:
            probe.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
            try:
                probe.bind(("127.0.0.1", port))
                return port
            except OSError:
                continue
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


def start(bin_dir, cluster, port):
    pg_ctl = bin_dir / "pg_ctl.exe"
    if command([pg_ctl, "status", "-D", cluster]).returncode == 0:
        return
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


def prepare_database(home):
    import psycopg

    cluster = home / "cluster"
    state_file = home / "database.json"
    if state_file.exists():
        state = json.loads(state_file.read_text(encoding="utf-8"))
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
    port = state["port"]
    if not (cluster / "PG_VERSION").is_file():
        if cluster.exists() or "admin" not in state:
            raise SetupError("O cluster PostgreSQL está incompleto ou ausente. Restaure uma cópia antes de continuar.")
        initialize(bin_dir, cluster, state["admin"])
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
