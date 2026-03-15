"""Application-based profile inhibitor for PowerPilot.

Monitors running processes and forces specific profiles when
certain applications are detected.
"""

import logging
import subprocess
import threading

log = logging.getLogger("powerpilot.inhibitor")


class AppInhibitor:
    """Monitors running apps and triggers profile overrides.

    When a configured app is detected, forces the associated profile.
    When the app exits, restores the previous profile.
    """

    def __init__(self, app_rules: dict[str, str], enabled: bool = False) -> None:
        """Initialize the inhibitor.

        Args:
            app_rules: Mapping of process name -> profile name.
                e.g., {"steam": "performance", "gamemoderun": "performance"}
            enabled: Whether inhibition is active.
        """
        self._rules = app_rules
        self._enabled = enabled
        self._running = False
        self._thread: threading.Thread | None = None
        self._current_inhibitor: str | None = None
        self._on_inhibit_callback = None
        self._on_release_callback = None
        self._poll_interval = 10  # seconds

    @property
    def enabled(self) -> bool:
        return self._enabled

    @enabled.setter
    def enabled(self, value: bool) -> None:
        self._enabled = value
        if not value:
            self.stop()

    @property
    def active_inhibitor(self) -> str | None:
        """Process name currently inhibiting, or None."""
        return self._current_inhibitor

    def on_inhibit(self, callback) -> None:
        """Register callback for when an app triggers inhibition.

        Args:
            callback: Called with (process_name, target_profile).
        """
        self._on_inhibit_callback = callback

    def on_release(self, callback) -> None:
        """Register callback for when inhibition is released.

        Args:
            callback: Called with no arguments.
        """
        self._on_release_callback = callback

    def start(self) -> None:
        """Start monitoring for inhibiting apps."""
        if not self._enabled or self._running:
            return

        self._running = True
        self._thread = threading.Thread(target=self._poll_loop, daemon=True)
        self._thread.start()
        log.info("App inhibitor started (monitoring: %s)", list(self._rules.keys()))

    def stop(self) -> None:
        """Stop the inhibitor."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=5)
        if self._current_inhibitor:
            self._release()

    def check_once(self) -> str | None:
        """Check running processes once against rules.

        Returns:
            Target profile name if an inhibiting app is found, None otherwise.
        """
        running = self._get_running_processes()
        for process_name, target_profile in self._rules.items():
            if process_name.lower() in running:
                return target_profile
        return None

    def _poll_loop(self) -> None:
        """Continuously check for inhibiting apps."""
        import time

        while self._running:
            try:
                target = self.check_once()
                if target and not self._current_inhibitor:
                    # Find which process triggered it
                    running = self._get_running_processes()
                    for name in self._rules:
                        if name.lower() in running:
                            self._inhibit(name, self._rules[name])
                            break
                elif not target and self._current_inhibitor:
                    self._release()
            except Exception as e:
                log.debug("Inhibitor poll error: %s", e)

            time.sleep(self._poll_interval)

    def _inhibit(self, process_name: str, target_profile: str) -> None:
        """Activate inhibition."""
        self._current_inhibitor = process_name
        log.info(
            "App inhibitor triggered: '%s' → profile '%s'",
            process_name,
            target_profile,
        )
        if self._on_inhibit_callback:
            try:
                self._on_inhibit_callback(process_name, target_profile)
            except Exception as e:
                log.error("Inhibit callback error: %s", e)

    def _release(self) -> None:
        """Release inhibition."""
        log.info("App inhibitor released (was: '%s')", self._current_inhibitor)
        self._current_inhibitor = None
        if self._on_release_callback:
            try:
                self._on_release_callback()
            except Exception as e:
                log.error("Release callback error: %s", e)

    def _get_running_processes(self) -> set[str]:
        """Get set of running process names (lowercase)."""
        try:
            result = subprocess.run(
                ["ps", "-eo", "comm="],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode == 0:
                return {
                    line.strip().lower()
                    for line in result.stdout.splitlines()
                    if line.strip()
                }
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass
        return set()
