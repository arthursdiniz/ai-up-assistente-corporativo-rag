"""Load explicit Windows user settings without printing secrets."""
import os


def load_user_environment() -> None:
    if os.name != "nt":
        return
    import winreg

    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment")
    except FileNotFoundError:
        return
    with key:
        for name in ("DATABASE_URL", "DATABASE_USERNAME", "DATABASE_PASSWORD", "DATABASE_HOST",
                     "DATABASE_PORT", "DATABASE_NAME", "SECRET_KEY"):
            if os.environ.get(name):
                continue
            try:
                value, _ = winreg.QueryValueEx(key, name)
            except FileNotFoundError:
                continue
            if value:
                os.environ[name] = str(value)
