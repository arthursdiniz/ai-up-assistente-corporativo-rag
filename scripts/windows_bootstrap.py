"""Small Windows setup primitives. Never log command arguments or exception payloads."""
from contextlib import contextmanager
import csv
import hashlib
import logging
import os
from pathlib import Path
import shutil
import subprocess
from tempfile import NamedTemporaryFile
from urllib.request import urlopen


log = logging.getLogger("aiup.setup")


class SetupError(RuntimeError):
    pass


def say(message):
    print(message, flush=True)
    log.info(message)


def consent(message):
    try:
        return input(message + " [s/N] ").strip().casefold() in {"s", "sim"}
    except EOFError:
        return False


def require_space(path, gib):
    if shutil.disk_usage(path).free < gib * 1024**3:
        raise SetupError(f"Libere ao menos {gib} GB na unidade que contém {path} e tente novamente.")


def command(args, *, timeout=30, live=False, quiet=False):
    try:
        output = {"stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL} if quiet else {"capture_output": not live}
        return subprocess.run(args, **output, text=True, errors="replace", timeout=timeout)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise SetupError(f"Não foi possível executar {Path(args[0]).name}. Confira acesso, antivírus e tempo de execução.") from exc


def secure_directory(path):
    if path.is_symlink() or path.is_junction():
        raise SetupError("A pasta de dados da instalação não pode ser um link ou junção.")
    path.mkdir(parents=True, exist_ok=True)
    result = command(["whoami.exe", "/user", "/fo", "csv", "/nh"])
    row = next(csv.reader(result.stdout.strip().splitlines()), [])
    sid = row[-1] if row else ""
    if result.returncode != 0 or not sid.startswith("S-1-"):
        raise SetupError("Não foi possível identificar a conta do Windows para proteger os dados.")
    applied = command(["icacls.exe", str(path), "/inheritance:r", "/grant:r", f"*{sid}:(OI)(CI)F", "*S-1-5-18:(OI)(CI)F"])
    if applied.returncode != 0:
        raise SetupError("Não foi possível proteger a pasta de dados local. Use uma unidade NTFS e sua conta habitual.")


@contextmanager
def setup_lock(path):
    import msvcrt

    with path.open("a+b") as stream:
        stream.seek(0)
        try:
            msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError as exc:
            raise SetupError("Já existe outra preparação do AI-Up em andamento. Aguarde e tente novamente.") from exc
        try:
            yield
        finally:
            stream.seek(0)
            msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)


def write_text(path, content, *, replace=False):
    # The parent for credentials is already protected by a Windows ACL.
    with NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent, delete=False) as stream:
        temporary = Path(stream.name)
        stream.write(content)
        stream.flush()
        os.fsync(stream.fileno())
    try:
        if replace:
            temporary.replace(path)
        elif os.name == "nt":
            temporary.rename(path)  # Windows rename fails if the destination exists.
        else:
            # A hard link publishes the complete file atomically without overwriting an existing file.
            os.link(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def download(url, digest, target, max_bytes):
    partial = target.with_suffix(target.suffix + ".partial")
    size = 0
    checksum = hashlib.sha256()
    try:
        with urlopen(url, timeout=30) as response, partial.open("wb") as stream:
            if not response.geturl().startswith("https://"):
                raise SetupError("O fornecedor redirecionou o download para uma conexão sem HTTPS.")
            while block := response.read(1024 * 1024):
                size += len(block)
                if size > max_bytes:
                    raise SetupError("O arquivo baixado ultrapassou o tamanho esperado.")
                checksum.update(block)
                stream.write(block)
                if size % (32 * 1024**2) == 0:
                    print(f"  {size // 1024**2} MB recebidos", flush=True)
        if checksum.hexdigest() != digest:
            raise SetupError("SHA-256 inválido. O arquivo não foi usado.")
        partial.replace(target)
    except OSError as exc:
        raise SetupError("Falha no download. Confira internet, espaço, permissões e tente novamente.") from exc
    finally:
        partial.unlink(missing_ok=True)


def install_vendor(name, package, official_url, home, fallback, *, installed=None):
    winget = shutil.which("winget.exe")
    if winget and consent(f"Instalar {name} via WinGet? O fornecedor pode solicitar licença e o Windows pode solicitar UAC."):
        try:
            result = command([winget, "install", "--id", package, "--exact", "--source", "winget"], live=True, timeout=None)
            log.info("WinGet %s: código %s", package, result.returncode)
        except SetupError:
            result = None
        if (result and result.returncode == 0) or (installed and installed()):
            return True
        say("O WinGet não concluiu a instalação. Se o Windows solicitou reinício, reinicie antes de repetir.")
    if consent(f"Baixar e abrir o instalador oficial verificado de {name}? O instalador pode pedir licença ou UAC."):
        url, digest, filename, max_gib = fallback
        require_space(home, max_gib + 1)
        target = home / filename
        valid = False
        if target.is_file():
            with target.open("rb") as stream:
                valid = hashlib.file_digest(stream, "sha256").hexdigest() == digest
        if not valid:
            say(f"Baixando {name} com verificação SHA-256...")
            download(url, digest, target, max_gib * 1024**3)
        result = command([str(target)], live=True, timeout=None)
        log.info("Instalador oficial %s: código %s", name, result.returncode)
        if result.returncode == 0:
            target.unlink(missing_ok=True)
            return True
        say("O instalador foi interrompido. Se solicitado, reinicie o Windows antes de continuar.")
    say(f"Instalação oficial de {name}: {official_url}")
    return False
