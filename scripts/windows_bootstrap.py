"""Small Windows setup primitives. Never log command arguments or exception payloads."""
from contextlib import contextmanager
import hashlib
from http.client import HTTPException
import logging
import os
from pathlib import Path
import shutil
import ssl
import subprocess
from tempfile import NamedTemporaryFile
from urllib.error import HTTPError, URLError
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


def command(args, *, timeout=30, live=False, quiet=False, env=None):
    try:
        output = {"stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL} if quiet else {"capture_output": not live}
        return subprocess.run(args, **output, text=True, errors="replace", timeout=timeout, env=env)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise SetupError(f"Não foi possível executar {Path(args[0]).name}. Confira acesso, antivírus e tempo de execução.") from exc


def reject_link(path):
    if path.is_symlink() or path.is_junction():
        raise SetupError(f"O caminho {path.name} da instalação não pode ser um link ou junção.")


def secure_directory(path):
    for directory in (path.parent.parent, path.parent, path):
        reject_link(directory)
    path.mkdir(parents=True, exist_ok=True)
    # Replace the DACL, including any explicit grants left on a pre-existing folder.
    script = """
$ErrorActionPreference = 'Stop'
$sid = [Security.Principal.WindowsIdentity]::GetCurrent().User
$system = [Security.Principal.SecurityIdentifier]::new('S-1-5-18')
$acl = [Security.AccessControl.DirectorySecurity]::new()
$acl.SetAccessRuleProtection($true, $false)
foreach ($identity in @($sid, $system)) {
    $rule = [Security.AccessControl.FileSystemAccessRule]::new($identity, 'FullControl',
        'ContainerInherit,ObjectInherit', 'None', 'Allow')
    $acl.AddAccessRule($rule)
}
[IO.Directory]::SetAccessControl($env:AIUP_PRIVATE_ACL_PATH, $acl)
foreach ($name in @('settings.env', 'database.json', 'setup.log', 'postgresql.log')) {
    $file = [IO.Path]::Combine($env:AIUP_PRIVATE_ACL_PATH, $name)
    if (-not [IO.File]::Exists($file)) { continue }
    if ([IO.File]::GetAttributes($file).HasFlag([IO.FileAttributes]::ReparsePoint)) { throw 'Private file is a link.' }
    $fileAcl = [Security.AccessControl.FileSecurity]::new()
    $fileAcl.SetAccessRuleProtection($true, $false)
    foreach ($identity in @($sid, $system)) {
        $fileAcl.AddAccessRule([Security.AccessControl.FileSystemAccessRule]::new($identity, 'FullControl', 'Allow'))
    }
    [IO.File]::SetAccessControl($file, $fileAcl)
}
"""
    shell = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32/WindowsPowerShell/v1.0/powershell.exe"
    applied = command([shell, "-NoProfile", "-NonInteractive", "-Command", script],
                      env={**os.environ, "AIUP_PRIVATE_ACL_PATH": str(path)})
    if applied.returncode != 0:
        raise SetupError("Não foi possível proteger a pasta de dados local. Use uma unidade NTFS e sua conta habitual.")


@contextmanager
def setup_lock(path):
    import msvcrt

    reject_link(path)
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
    reject_link(path)
    temporary = None
    try:
        with NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent, delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        if replace:
            temporary.replace(path)
        elif os.name == "nt":
            temporary.rename(path)  # Windows rename fails if the destination exists.
        else:
            # A hard link publishes the complete file atomically without overwriting an existing file.
            os.link(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def download(url, digest, target, max_bytes):
    reject_link(target)
    if not url.startswith("https://"):
        raise SetupError("O endereço do fornecedor precisa usar HTTPS.")
    partial = None
    size = 0
    checksum = hashlib.sha256()
    try:
        with urlopen(url, timeout=30) as response, NamedTemporaryFile(
                dir=target.parent, prefix=target.name + "-", suffix=".partial", delete=False) as stream:
            partial = Path(stream.name)
            if not response.geturl().startswith("https://"):
                raise SetupError("O fornecedor redirecionou o download para uma conexão sem HTTPS.")
            expected = response.headers.get("Content-Length") if hasattr(response, "headers") else None
            total = int(expected) if expected and expected.isdecimal() else None
            if total is not None and total > max_bytes:
                raise SetupError("O arquivo anunciado pelo fornecedor ultrapassa o tamanho esperado.")
            progress_at = 8 * 1024**2
            while block := response.read(1024 * 1024):
                size += len(block)
                if size > max_bytes:
                    raise SetupError("O arquivo baixado ultrapassou o tamanho esperado.")
                checksum.update(block)
                stream.write(block)
                if size >= progress_at:
                    total_text = f" de {total / 1024**2:.0f} MB" if total else ""
                    print(f"  {size / 1024**2:.0f} MB{total_text} recebidos", flush=True)
                    progress_at = size + 8 * 1024**2
        if total is not None and size != total:
            raise SetupError("O download ficou incompleto. Confira a conexão e reabra o atalho para tentar novamente.")
        if checksum.hexdigest() != digest:
            raise SetupError("SHA-256 inválido. O arquivo não foi usado.")
        partial.replace(target)
    except HTTPError as exc:
        raise SetupError(f"O fornecedor retornou HTTP {exc.code}. Confira o acesso à rede ou use o instalador oficial indicado.") from exc
    except URLError as exc:
        if isinstance(exc.reason, ssl.SSLError):
            raise SetupError("O certificado HTTPS não pôde ser validado. Confira relógio, proxy e certificados do Windows.") from exc
        raise SetupError("Não foi possível acessar o fornecedor. Confira internet, proxy ou firewall e tente novamente.") from exc
    except (OSError, HTTPException) as exc:
        raise SetupError("Falha no download. Confira internet, espaço, permissões e tente novamente.") from exc
    finally:
        if partial is not None:
            partial.unlink(missing_ok=True)


def file_sha256(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


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
        reject_link(target)
        valid = target.is_file() and file_sha256(target) == digest
        if not valid:
            say(f"Baixando {name} com verificação SHA-256...")
            try:
                download(url, digest, target, max_gib * 1024**3)
            except SetupError:
                say(f"Alternativa manual de {name}: {official_url}")
                raise
        result = command([str(target)], live=True, timeout=None)
        log.info("Instalador oficial %s: código %s", name, result.returncode)
        if result.returncode == 0:
            target.unlink(missing_ok=True)
            return True
        say("O instalador foi interrompido. Se solicitado, reinicie o Windows antes de continuar.")
    say(f"Instalação oficial de {name}: {official_url}")
    return False
