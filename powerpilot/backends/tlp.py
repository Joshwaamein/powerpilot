"""TLP backend for PowerPilot.

Manages TLP configuration profiles via symlink in /etc/tlp.d/.
Uses a polkit helper script for privileged operations.
"""

import logging
import os
import subprocess
import shutil
from pathlib import Path

from .base import PowerBackend

log = logging.getLogger("powerpilot.backends.tlp")

# TLP configuration paths
TLP_CONF_DIR = Path("/etc/tlp.d")
TLP_POWERPILOT_CONF = TLP_CONF_DIR / "99-powerpilot.conf"

# PowerPilot's TLP profile storage
PROFILES_DIR_SYSTEM = Path("/usr/share/powerpilot/tlp-profiles")


def _get_user_profiles_dir() -> Path:
    """Get user's TLP profiles directory."""
    xdg_config = os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")
    return Path(xdg_config) / "powerpilot" / "tlp-profiles"


class TLPBackend(PowerBackend):
    """Backend using TLP for power management."""

    def __init__(self) -> None:
        self._profiles_dir = _get_user_profiles_dir()
        self._ensure_profiles_dir()

    @property
    def name(self) -> str:
        return "TLP"

    @property
    def backend_type(self) -> str:
        return "tlp"

    @property
    def supports_tlp_auto(self) -> bool:
        return True

    def _ensure_profiles_dir(self) -> None:
        """Create user profiles directory and copy defaults if needed."""
        self._profiles_dir.mkdir(parents=True, exist_ok=True)

        # Copy default profiles from system dir if user dir is empty
        if not any(self._profiles_dir.glob("*.conf")):
            if PROFILES_DIR_SYSTEM.exists():
                for conf in PROFILES_DIR_SYSTEM.glob("*.conf"):
                    dest = self._profiles_dir / conf.name
                    if not dest.exists():
                        shutil.copy2(conf, dest)
                        log.info("Copied default TLP profile: %s", conf.name)

    def get_available_profiles(self) -> list[str]:
        """Get list of available TLP profile names.

        Scans the user profiles directory for .conf files.

        Returns:
            List of profile names (filename without .conf extension).
        """
        profiles = []
        for conf in sorted(self._profiles_dir.glob("*.conf")):
            profiles.append(conf.stem)

        if not profiles:
            log.warning("No TLP profiles found in %s", self._profiles_dir)

        return profiles

    def get_active_profile(self) -> str | None:
        """Get the currently active TLP profile.

        Checks what the /etc/tlp.d/99-powerpilot.conf symlink points to.

        Returns:
            Profile name, 'tlp-auto' if no PowerPilot config, or None.
        """
        if not TLP_POWERPILOT_CONF.exists():
            return "tlp-auto"  # No PowerPilot override = TLP defaults

        if TLP_POWERPILOT_CONF.is_symlink():
            target = TLP_POWERPILOT_CONF.resolve()
            return target.stem

        # It's a regular file — read a comment marker we may have left
        try:
            content = TLP_POWERPILOT_CONF.read_text()
            for line in content.splitlines():
                if line.startswith("# PowerPilot profile:"):
                    return line.split(":", 1)[1].strip()
        except (OSError, IOError):
            pass

        return None

    def set_profile(self, profile: str) -> bool:
        """Set the active TLP profile.

        Creates/updates the symlink at /etc/tlp.d/99-powerpilot.conf
        and runs 'tlp start' to apply.

        Uses pkexec for privilege escalation.

        Args:
            profile: Profile name matching a .conf file in profiles dir.

        Returns:
            True if successful.
        """
        profile_path = self._profiles_dir / f"{profile}.conf"

        if not profile_path.exists():
            log.error("TLP profile '%s' not found at %s", profile, profile_path)
            return False

        return self._apply_profile(str(profile_path))

    def apply_tlp_auto(self) -> bool:
        """Switch to TLP auto mode by removing the PowerPilot config.

        Returns:
            True if successful.
        """
        return self._remove_powerpilot_conf()

    def _apply_profile(self, profile_path: str) -> bool:
        """Apply a TLP profile using the helper script.

        Args:
            profile_path: Absolute path to the .conf file.

        Returns:
            True if successful.
        """
        helper = self._find_helper()
        if not helper:
            log.error("PowerPilot helper script not found")
            return False

        try:
            result = subprocess.run(
                ["pkexec", helper, "apply", profile_path],
                capture_output=True,
                text=True,
                timeout=30,
            )
            if result.returncode == 0:
                log.info("Applied TLP profile: %s", profile_path)
                return True
            else:
                log.error("Helper failed: %s", result.stderr)
        except subprocess.TimeoutExpired:
            log.error("Helper script timed out")
        except FileNotFoundError:
            log.error("pkexec not found — cannot escalate privileges")

        return False

    def _remove_powerpilot_conf(self) -> bool:
        """Remove the PowerPilot TLP config to restore TLP defaults."""
        helper = self._find_helper()
        if not helper:
            log.error("PowerPilot helper script not found")
            return False

        try:
            result = subprocess.run(
                ["pkexec", helper, "remove"],
                capture_output=True,
                text=True,
                timeout=30,
            )
            if result.returncode == 0:
                log.info("Removed PowerPilot TLP config — TLP auto mode")
                return True
            else:
                log.error("Helper remove failed: %s", result.stderr)
        except (subprocess.TimeoutExpired, FileNotFoundError) as e:
            log.error("Failed to remove TLP config: %s", e)

        return False

    def _find_helper(self) -> str | None:
        """Find the PowerPilot helper script.

        Search order:
        1. POWERPILOT_HELPER_PATH environment variable
        2. System install locations
        3. Relative to package (dev mode)
        4. PATH lookup
        """
        # 1. Environment variable override
        env_path = os.environ.get("POWERPILOT_HELPER_PATH")
        if env_path and os.path.isfile(env_path) and os.access(env_path, os.X_OK):
            log.debug("Helper found via POWERPILOT_HELPER_PATH: %s", env_path)
            return env_path

        # 2. System install locations
        candidates = [
            Path("/usr/lib/powerpilot/powerpilot-helper"),
            Path("/usr/local/lib/powerpilot/powerpilot-helper"),
        ]

        # 3. Relative to package (dev mode) — try multiple levels
        pkg_dir = Path(__file__).parent.parent
        candidates.extend([
            pkg_dir / "data" / "powerpilot-helper",
            pkg_dir.parent / "data" / "powerpilot-helper",
        ])

        for candidate in candidates:
            if candidate.exists() and os.access(candidate, os.X_OK):
                log.debug("Helper found at: %s", candidate)
                return str(candidate)

        # 4. PATH lookup
        helper = shutil.which("powerpilot-helper")
        if helper:
            log.debug("Helper found in PATH: %s", helper)
            return helper

        return None


def get_tlp_status() -> dict:
    """Get current TLP status information.

    Returns:
        Dictionary with TLP status fields.
    """
    status = {
        "enabled": False,
        "mode": "unknown",
        "power_source": "unknown",
    }

    try:
        result = subprocess.run(
            ["tlp-stat", "-s"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            for line in result.stdout.splitlines():
                line = line.strip()
                if line.startswith("State"):
                    status["enabled"] = "enabled" in line
                elif line.startswith("Mode"):
                    parts = line.split("=")
                    if len(parts) > 1:
                        status["mode"] = parts[1].strip()
                elif line.startswith("Power source"):
                    parts = line.split("=")
                    if len(parts) > 1:
                        status["power_source"] = parts[1].strip()
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass

    return status
