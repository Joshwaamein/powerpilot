"""Backend switcher for PowerPilot.

Handles switching between power-profiles-daemon and TLP backends,
including package installation/removal and service management.
"""

import logging
import os
import shutil
import subprocess
import sys
from pathlib import Path

log = logging.getLogger("powerpilot.switcher")

# Package names for each backend
BACKEND_PACKAGES = {
    "tlp": ["tlp", "tlp-rdw"],
    "ppd": ["power-profiles-daemon"],
}

# Service names
BACKEND_SERVICES = {
    "tlp": "tlp",
    "ppd": "power-profiles-daemon",
}


class BackendSwitcher:
    """Handles switching between PPD and TLP backends."""

    def get_current_backend(self) -> str:
        """Detect which backend is currently active.

        Returns:
            'tlp', 'ppd', or 'none'.
        """
        if self._is_service_active("tlp") or self._is_tlp_enabled():
            return "tlp"
        if self._is_service_active("power-profiles-daemon"):
            return "ppd"
        return "none"

    def get_alternative_backend(self) -> str | None:
        """Get the backend that is NOT currently active.

        Returns:
            'tlp' or 'ppd', or None if current is 'none'.
        """
        current = self.get_current_backend()
        if current == "tlp":
            return "ppd"
        elif current == "ppd":
            return "tlp"
        return None

    def can_switch_to(self, target: str) -> tuple[bool, str]:
        """Check if we can switch to the target backend.

        Args:
            target: 'tlp' or 'ppd'.

        Returns:
            Tuple of (can_switch, reason).
        """
        if target not in ("tlp", "ppd"):
            return False, f"Invalid backend: {target}. Must be 'tlp' or 'ppd'."

        current = self.get_current_backend()
        if current == target:
            return False, f"Already using {target} backend."

        # Check apt is available
        if not shutil.which("apt"):
            return False, "apt package manager not found. Only Debian/Ubuntu supported."

        # Check pkexec is available
        if not shutil.which("pkexec"):
            return False, "pkexec not found. Cannot escalate privileges."

        # Check helper script exists
        helper = self._find_helper()
        if not helper:
            return False, "PowerPilot helper script not found."

        return True, "Ready to switch."

    def switch_to(self, target: str) -> tuple[bool, str]:
        """Switch to the specified backend.

        Uses pkexec + helper script for privileged operations.

        Args:
            target: 'tlp' or 'ppd'.

        Returns:
            Tuple of (success, message).
        """
        can_switch, reason = self.can_switch_to(target)
        if not can_switch:
            log.error("Cannot switch to %s: %s", target, reason)
            return False, reason

        helper = self._find_helper()
        log.info("Switching backend to %s via helper: %s", target, helper)

        try:
            result = subprocess.run(
                ["pkexec", helper, "switch-backend", target],
                capture_output=True,
                text=True,
                timeout=120,  # Package install can take a while
            )

            if result.returncode == 0:
                log.info("Backend switched to %s successfully", target)

                # Copy TLP profiles if switching to TLP
                if target == "tlp":
                    self._ensure_tlp_profiles()

                return True, f"Switched to {target} successfully."
            else:
                error = result.stderr.strip() or result.stdout.strip()
                log.error("Backend switch failed: %s", error)
                return False, f"Switch failed: {error}"

        except subprocess.TimeoutExpired:
            log.error("Backend switch timed out")
            return False, "Switch timed out (>120s). Check your internet connection."
        except FileNotFoundError:
            log.error("pkexec not found")
            return False, "pkexec not found. Cannot escalate privileges."

    def restart_app(self) -> None:
        """Restart the PowerPilot application.

        Uses os.execv to replace the current process.
        """
        log.info("Restarting PowerPilot...")
        python = sys.executable
        script = sys.argv[0]
        os.execv(python, [python, script])

    def _is_service_active(self, service: str) -> bool:
        """Check if a systemd service is active."""
        try:
            result = subprocess.run(
                ["systemctl", "is-active", "--quiet", service],
                capture_output=True,
                timeout=5,
            )
            return result.returncode == 0
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return False

    def _is_tlp_enabled(self) -> bool:
        """Check if TLP is enabled (it's a oneshot service, may show inactive)."""
        try:
            result = subprocess.run(
                ["tlp-stat", "-s"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            return result.returncode == 0 and "State          = enabled" in result.stdout
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return False

    def _find_helper(self) -> str | None:
        """Find the PowerPilot helper script."""
        # Check env var
        env_path = os.environ.get("POWERPILOT_HELPER_PATH")
        if env_path and os.path.isfile(env_path) and os.access(env_path, os.X_OK):
            return env_path

        candidates = [
            Path("/usr/lib/powerpilot/powerpilot-helper"),
            Path("/usr/local/lib/powerpilot/powerpilot-helper"),
            Path(__file__).parent.parent / "data" / "powerpilot-helper",
        ]

        for c in candidates:
            if c.exists() and os.access(c, os.X_OK):
                return str(c)

        helper = shutil.which("powerpilot-helper")
        return helper

    def _ensure_tlp_profiles(self) -> None:
        """Copy default TLP profiles to user config dir if needed."""
        xdg_config = os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")
        profiles_dir = Path(xdg_config) / "powerpilot" / "tlp-profiles"
        profiles_dir.mkdir(parents=True, exist_ok=True)

        # Source from package
        src_dirs = [
            Path("/usr/share/powerpilot/tlp-profiles"),
            Path(__file__).parent.parent / "tlp-profiles",
        ]

        for src_dir in src_dirs:
            if src_dir.exists():
                for conf in src_dir.glob("*.conf"):
                    dest = profiles_dir / conf.name
                    if not dest.exists():
                        import shutil as sh
                        sh.copy2(conf, dest)
                        log.info("Copied TLP profile: %s", conf.name)
                break
