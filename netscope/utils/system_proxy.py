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


def get_ca_cert_info() -> dict | None:
    """
    Return cert metadata dict or None.
    Keys: subject, not_before, not_after, days_left, path (str)
    """
    cert_path = get_ca_cert_path()
    if not cert_path:
        return None
    try:
        import datetime
        from cryptography import x509
        with open(cert_path, "rb") as f:
            cert = x509.load_pem_x509_certificate(f.read())
        try:
            cn_attrs = cert.subject.get_attributes_for_oid(x509.NameOID.COMMON_NAME)
            subject = cn_attrs[0].value if cn_attrs else "알 수 없음"
        except Exception:
            subject = "알 수 없음"
        try:
            not_before = cert.not_valid_before_utc
            not_after  = cert.not_valid_after_utc
            now        = datetime.datetime.now(tz=datetime.timezone.utc)
        except AttributeError:
            # cryptography < 42
            not_before = cert.not_valid_before.replace(tzinfo=datetime.timezone.utc)
            not_after  = cert.not_valid_after.replace(tzinfo=datetime.timezone.utc)
            now        = datetime.datetime.now(tz=datetime.timezone.utc)
        days_left = (not_after - now).days
        return {
            "subject":    subject,
            "not_before": not_before,
            "not_after":  not_after,
            "days_left":  days_left,
            "path":       str(cert_path),
        }
    except ImportError:
        return {"subject": "cryptography 미설치", "path": str(cert_path),
                "not_before": None, "not_after": None, "days_left": None}
    except Exception:
        return None


def generate_ca_cert() -> tuple[bool, str]:
    """
    Generate mitmproxy CA certificate (creates ~/.mitmproxy/ if needed).
    Returns (success, message).
    """
    store_dir = Path.home() / ".mitmproxy"
    store_dir.mkdir(parents=True, exist_ok=True)
    code = (
        "import sys; from pathlib import Path\n"
        "try:\n"
        "    from mitmproxy.certs import CertStore\n"
        "    d = Path.home() / '.mitmproxy'\n"
        "    d.mkdir(exist_ok=True)\n"
        "    try:\n"
        "        CertStore.create_store(d, 'mitmproxy', 2048)\n"
        "    except TypeError:\n"
        "        CertStore.create_store(d, 'mitmproxy')\n"
        "    print('OK')\n"
        "except Exception as e:\n"
        "    print(f'ERR:{e}')\n"
    )
    try:
        result = subprocess.run(
            [sys.executable, "-c", code],
            capture_output=True, text=True,
            encoding="utf-8", errors="replace",
            timeout=30,
        )
        out = (result.stdout or "").strip()
        if out.startswith("ERR:"):
            return False, f"인증서 생성 실패:\n{out[4:]}"
        if get_ca_cert_path():
            return True, f"CA 인증서가 생성되었습니다.\n위치: {get_ca_cert_path()}"
        return False, "생성 명령은 완료되었으나 인증서 파일을 찾을 수 없습니다."
    except subprocess.TimeoutExpired:
        return False, "인증서 생성 시간이 초과되었습니다."
    except Exception as exc:
        return False, f"오류: {exc}"


def renew_ca_cert() -> tuple[bool, str]:
    """
    Remove existing CA cert files and regenerate.
    Returns (success, message).
    """
    store_dir = Path.home() / ".mitmproxy"
    for name in ("mitmproxy-ca.pem", "mitmproxy-ca-cert.pem",
                 "mitmproxy-ca-cert.p12", "mitmproxy-ca-cert.cer",
                 "mitmproxy-dhparam.pem"):
        p = store_dir / name
        try:
            p.unlink(missing_ok=True)
        except Exception:
            pass
    return generate_ca_cert()


def export_ca_cert(dest_path: str) -> tuple[bool, str]:
    """Copy the CA cert PEM to dest_path. Returns (success, message)."""
    import shutil
    cert = get_ca_cert_path()
    if not cert:
        return False, "내보낼 인증서 파일이 없습니다."
    try:
        shutil.copy2(cert, dest_path)
        return True, f"인증서를 내보냈습니다:\n{dest_path}"
    except Exception as exc:
        return False, f"내보내기 오류: {exc}"


def remove_ca_cert_windows() -> tuple[bool, str]:
    """Remove mitmproxy CA from Windows user Root trust store."""
    try:
        result = subprocess.run(
            ["certutil", "-delstore", "-user", "Root", "mitmproxy"],
            capture_output=True, text=True,
            encoding="utf-8", errors="replace",
        )
        if result.returncode == 0:
            return True, "CA 인증서가 신뢰 저장소에서 제거되었습니다."
        return False, f"제거 실패:\n{result.stderr.strip() or result.stdout.strip()}"
    except FileNotFoundError:
        return False, "certutil.exe를 찾을 수 없습니다."
    except Exception as exc:
        return False, f"오류: {exc}"


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
