from pathlib import Path


def test_windows_powershell_startup_script_is_ascii_compatible():
    script = Path("scripts/start_ai_up.ps1").read_bytes()

    assert script.isascii(), (
        "Windows PowerShell 5.1 reads UTF-8 files without a BOM as the legacy "
        "code page, which corrupts accented error messages."
    )
