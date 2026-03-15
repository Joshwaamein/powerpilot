"""Backend auto-detection and factory for PowerPilot.

Detects which power management service is active and returns
the appropriate backend.
"""

import logging
import subprocess

from .base import PowerBackend

log = logging.getLogger("powerpilot.backends")


def detect_backend(preferred: str = "auto") -> PowerBackend:
    """Detect and instantiate the appropriate power backend.

    Priority: TLP (if active) > PPD (if active) > sysfs fallback.

    Args:
        preferred: Backend preference from config.
            "auto" - auto-detect
            "tlp"  - force TLP
            "ppd"  - force power-profiles-daemon
            "sysfs" - sysfs-only (no daemon)

    Returns:
        Instantiated PowerBackend.
    """
    if preferred == "tlp":
        return _try_tlp() or _fallback()
    elif preferred == "ppd":
        return _try_ppd() or _fallback()
    elif preferred == "sysfs":
        return _fallback()

    # Auto-detect: check active services
    # Priority: TLP > PPD > sysfs
    tlp = _try_tlp()
    if tlp:
        return tlp

    ppd = _try_ppd()
    if ppd:
        return ppd

    return _fallback()


def _is_service_active(service: str) -> bool:
    """Check if a systemd service is currently active."""
    try:
        result = subprocess.run(
            ["systemctl", "is-active", "--quiet", service],
            capture_output=True,
            timeout=5,
        )
        return result.returncode == 0
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return False


def _try_tlp() -> "PowerBackend | None":
    """Try to initialize the TLP backend."""
    if _is_service_active("tlp"):
        from .tlp import TLPBackend

        log.info("TLP service is active, using TLP backend")
        return TLPBackend()

    # Also check if tlp command exists even if service shows inactive
    # (TLP service is a oneshot, so it may show inactive after boot)
    try:
        result = subprocess.run(
            ["tlp-stat", "-s"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0 and "State          = enabled" in result.stdout:
            from .tlp import TLPBackend

            log.info("TLP is enabled (detected via tlp-stat), using TLP backend")
            return TLPBackend()
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass

    return None


def _try_ppd() -> "PowerBackend | None":
    """Try to initialize the power-profiles-daemon backend."""
    if _is_service_active("power-profiles-daemon"):
        from .ppd import PPDBackend

        log.info("power-profiles-daemon is active, using PPD backend")
        return PPDBackend()

    return None


def _fallback() -> "PowerBackend":
    """Return the sysfs fallback backend."""
    from .base import SysfsBackend

    log.warning("No power daemon detected, using sysfs-only fallback backend")
    return SysfsBackend()
