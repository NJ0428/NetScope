"""
System proxy configuration utilities.

Supports Windows (WinINet registry) and macOS (networksetup).
"""

from __future__ import annotations

import ctypes
import subprocess
import sys
from pathlib import Path


def set_system_proxy(host: str = "127.0.0.1", port: int = 8888) -> bool:
    """Enable system HTTP/HTTPS proxy. Returns True on success."""
    if sys.platform == "win32":
        return _set_win_proxy(host, port)
    if sys.platform == "darwin":
        return _set_mac_proxy(host, port)
    return False


def clear_system_proxy() -> bool:
    """Disable system proxy. Returns True on success."""
    if sys.platform == "win32":
        return _clear_win_proxy()
    if sys.platform == "darwin":
        return _clear_mac_proxy()
    return False


def get_ca_cert_path() -> Path | None:
    """Return path to mitmproxy CA certificate, or None if not found."""
    cert = Path.home() / ".mitmproxy" / "mitmproxy-ca-cert.pem"
    return cert if cert.exists() else None


def install_ca_cert_windows() -> tuple[bool, str]:
    """
    Install mitmproxy CA certificate into the Windows user Root CA store.
    Returns (success, message).
    """
    cert = get_ca_cert_path()
    if cert is None:
        return (
            False,
            "인증서 파일을 찾을 수 없습니다.\n"
            "캡처를 한 번 시작하면 ~/.mitmproxy/ 에 자동으로 생성됩니다.",
        )
    try:
        result = subprocess.run(
            ["certutil", "-addstore", "-user", "Root", str(cert)],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        if result.returncode == 0:
            return True, "CA 인증서가 성공적으로 설치되었습니다."
        return False, f"설치 실패:\n{result.stderr.strip() or result.stdout.strip()}"
    except FileNotFoundError:
        return False, "certutil.exe를 찾을 수 없습니다 (Windows에서만 지원됩니다)."
    except Exception as exc:
        return False, f"오류: {exc}"


# ── Windows ────────────────────────────────────────────────────────────────


def _set_win_proxy(host: str, port: int) -> bool:
    try:
        import winreg  # type: ignore[import]

        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Internet Settings",
            0,
            winreg.KEY_SET_VALUE,
        )
        winreg.SetValueEx(key, "ProxyEnable", 0, winreg.REG_DWORD, 1)
        winreg.SetValueEx(key, "ProxyServer", 0, winreg.REG_SZ, f"{host}:{port}")
        winreg.SetValueEx(
            key,
            "ProxyOverride",
            0,
            winreg.REG_SZ,
            "localhost;127.*;10.*;172.16.*;192.168.*;<local>",
        )
        winreg.CloseKey(key)
        _win_broadcast()
        return True
    except Exception:
        return False


def _clear_win_proxy() -> bool:
    try:
        import winreg  # type: ignore[import]

        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Internet Settings",
            0,
            winreg.KEY_SET_VALUE,
        )
        winreg.SetValueEx(key, "ProxyEnable", 0, winreg.REG_DWORD, 0)
        winreg.CloseKey(key)
        _win_broadcast()
        return True
    except Exception:
        return False


def _win_broadcast():
    """Broadcast WinINet proxy change so browsers pick it up immediately."""
    try:
        INTERNET_OPTION_SETTINGS_CHANGED = 39
        INTERNET_OPTION_REFRESH = 37
        wininet = ctypes.windll.wininet  # type: ignore[attr-defined]
        wininet.InternetSetOptionW(0, INTERNET_OPTION_SETTINGS_CHANGED, 0, 0)
        wininet.InternetSetOptionW(0, INTERNET_OPTION_REFRESH, 0, 0)
    except Exception:
        pass


# ── macOS ──────────────────────────────────────────────────────────────────


def _mac_get_services() -> list[str]:
    """List active network services on macOS."""
    try:
        out = subprocess.check_output(
            ["networksetup", "-listallnetworkservices"],
            text=True,
            stderr=subprocess.DEVNULL,
        )
        return [line.strip() for line in out.splitlines()[1:] if line.strip()]
    except Exception:
        return []


def _set_mac_proxy(host: str, port: int) -> bool:
    ok = True
    for svc in _mac_get_services():
        for proto in ("web", "secureweb"):
            r = subprocess.run(
                ["networksetup", f"-set{proto}proxy", svc, host, str(port)],
                capture_output=True,
            )
            if r.returncode != 0:
                ok = False
    return ok


def _clear_mac_proxy() -> bool:
    ok = True
    for svc in _mac_get_services():
        for proto in ("web", "secureweb"):
            r = subprocess.run(
                ["networksetup", f"-set{proto}proxystate", svc, "off"],
                capture_output=True,
            )
            if r.returncode != 0:
                ok = False
    return ok
