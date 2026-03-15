"""Hardware detection for PowerPilot.

Auto-detects available power management capabilities:
- Screen backlight
- Keyboard backlight
- Bluetooth
- Wi-Fi
- Battery
- Refresh rate support
"""

import logging
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

log = logging.getLogger("powerpilot.hardware")


@dataclass
class BacklightInfo:
    """Screen backlight information."""

    path: Path
    max_brightness: int
    name: str

    @property
    def brightness(self) -> int:
        """Read current brightness value."""
        return int((self.path / "brightness").read_text().strip())

    @brightness.setter
    def brightness(self, value: int) -> None:
        """Set brightness value. Tries direct sysfs write, falls back to brightnessctl."""
        value = max(0, min(value, self.max_brightness))
        try:
            (self.path / "brightness").write_text(str(value))
        except PermissionError:
            log.debug("Direct brightness write failed (no permission), trying brightnessctl")
            self._set_brightness_ctl(value)

    def _set_brightness_ctl(self, value: int) -> None:
        """Set brightness using brightnessctl CLI tool."""
        import subprocess
        try:
            result = subprocess.run(
                ["brightnessctl", "-d", self.name, "set", str(value)],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode != 0:
                raise OSError(f"brightnessctl failed: {result.stderr}")
            log.debug("Set brightness via brightnessctl: %d", value)
        except FileNotFoundError:
            raise PermissionError(
                "Cannot set brightness: no write permission to sysfs and "
                "brightnessctl not installed. Install brightnessctl or run as root."
            )

    @property
    def brightness_percent(self) -> int:
        """Current brightness as a percentage."""
        return round(self.brightness * 100 / self.max_brightness)

    def set_percent(self, percent: int) -> None:
        """Set brightness as a percentage (0-100)."""
        percent = max(0, min(100, percent))
        self.brightness = round(self.max_brightness * percent / 100)


@dataclass
class KbdBacklightInfo:
    """Keyboard backlight information."""

    path: Path
    max_brightness: int
    name: str

    @property
    def brightness(self) -> int:
        """Read current keyboard backlight level."""
        return int((self.path / "brightness").read_text().strip())

    @brightness.setter
    def brightness(self, value: int) -> None:
        """Set keyboard backlight level."""
        value = max(0, min(value, self.max_brightness))
        (self.path / "brightness").write_text(str(value))


@dataclass
class BatteryInfo:
    """Battery information."""

    path: Path
    name: str

    @property
    def present(self) -> bool:
        """Check if battery is present."""
        try:
            status = (self.path / "status").read_text().strip()
            return status != "Unknown" or (self.path / "energy_now").exists()
        except (OSError, IOError):
            return False

    @property
    def status(self) -> str:
        """Battery status: Charging, Discharging, Full, Not charging."""
        try:
            return (self.path / "status").read_text().strip()
        except (OSError, IOError):
            return "Unknown"

    @property
    def charge_percent(self) -> int | None:
        """Current charge percentage."""
        try:
            now = int((self.path / "energy_now").read_text().strip())
            full = int((self.path / "energy_full").read_text().strip())
            if full > 0:
                return round(now * 100 / full)
        except (OSError, IOError, ValueError):
            pass
        # Try capacity file as fallback
        try:
            return int((self.path / "capacity").read_text().strip())
        except (OSError, IOError, ValueError):
            return None

    @property
    def power_draw_watts(self) -> float | None:
        """Current power draw in watts."""
        try:
            power = int((self.path / "power_now").read_text().strip())
            return round(power / 1_000_000, 1)
        except (OSError, IOError, ValueError):
            return None

    @property
    def time_remaining_hours(self) -> float | None:
        """Estimated hours remaining (only when discharging)."""
        if self.status != "Discharging":
            return None
        try:
            now = int((self.path / "energy_now").read_text().strip())
            power = int((self.path / "power_now").read_text().strip())
            if power > 0:
                return round(now / power, 1)
        except (OSError, IOError, ValueError):
            pass
        return None

    @property
    def health_percent(self) -> int | None:
        """Battery health (full capacity vs design capacity)."""
        try:
            full = int((self.path / "energy_full").read_text().strip())
            design = int((self.path / "energy_full_design").read_text().strip())
            if design > 0:
                return round(full * 100 / design)
        except (OSError, IOError, ValueError):
            return None

    @property
    def on_ac(self) -> bool:
        """Check if on AC power."""
        return self.status in ("Charging", "Full", "Not charging")


@dataclass
class WifiInfo:
    """Wi-Fi interface information."""

    interface: str

    @property
    def power_save(self) -> bool | None:
        """Check if Wi-Fi power save is enabled."""
        try:
            result = subprocess.run(
                ["iw", "dev", self.interface, "get", "power_save"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode == 0:
                return "on" in result.stdout.lower()
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass
        return None

    def set_power_save(self, enabled: bool) -> bool:
        """Set Wi-Fi power save. Returns True on success."""
        state = "on" if enabled else "off"
        try:
            result = subprocess.run(
                ["iw", "dev", self.interface, "set", "power_save", state],
                capture_output=True,
                text=True,
                timeout=5,
            )
            return result.returncode == 0
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return False


@dataclass
class BluetoothInfo:
    """Bluetooth information."""

    rfkill_index: int | None = None

    @property
    def available(self) -> bool:
        """Check if bluetooth hardware exists."""
        return self.rfkill_index is not None

    @property
    def enabled(self) -> bool:
        """Check if bluetooth is enabled (not soft-blocked)."""
        try:
            result = subprocess.run(
                ["rfkill", "list", "bluetooth"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode == 0:
                return "Soft blocked: no" in result.stdout
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass
        return False

    def set_enabled(self, enabled: bool) -> bool:
        """Enable or disable bluetooth. Returns True on success."""
        action = "unblock" if enabled else "block"
        try:
            result = subprocess.run(
                ["rfkill", action, "bluetooth"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            return result.returncode == 0
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return False


@dataclass
class HardwareCapabilities:
    """Detected hardware capabilities."""

    backlight: BacklightInfo | None = None
    kbd_backlight: KbdBacklightInfo | None = None
    battery: BatteryInfo | None = None
    wifi: WifiInfo | None = None
    bluetooth: BluetoothInfo | None = None

    def summary(self) -> dict[str, bool]:
        """Return a summary of detected capabilities."""
        return {
            "screen_backlight": self.backlight is not None,
            "keyboard_backlight": self.kbd_backlight is not None,
            "battery": self.battery is not None,
            "wifi": self.wifi is not None,
            "bluetooth": self.bluetooth is not None and self.bluetooth.available,
        }


def detect_hardware() -> HardwareCapabilities:
    """Auto-detect all available hardware controls.

    Returns:
        HardwareCapabilities with detected devices.
    """
    caps = HardwareCapabilities()

    caps.backlight = _detect_backlight()
    caps.kbd_backlight = _detect_kbd_backlight()
    caps.battery = _detect_battery()
    caps.wifi = _detect_wifi()
    caps.bluetooth = _detect_bluetooth()

    summary = caps.summary()
    log.info("Hardware detection complete: %s", summary)

    return caps


def _detect_backlight() -> BacklightInfo | None:
    """Detect the primary screen backlight."""
    backlight_dir = Path("/sys/class/backlight")
    if not backlight_dir.exists():
        return None

    # Prefer real hardware backlights over firmware/platform
    best = None
    for entry in sorted(backlight_dir.iterdir()):
        try:
            bl_type = (entry / "type").read_text().strip()
            max_br = int((entry / "max_brightness").read_text().strip())
            if max_br <= 0:
                continue

            info = BacklightInfo(path=entry, max_brightness=max_br, name=entry.name)

            # Prefer raw > firmware > platform
            if bl_type == "raw" or best is None:
                best = info
                if bl_type == "raw":
                    break
        except (OSError, IOError, ValueError) as e:
            log.debug("Skipping backlight %s: %s", entry.name, e)
            continue

    if best:
        log.info("Detected backlight: %s (max: %d)", best.name, best.max_brightness)
    return best


def _detect_kbd_backlight() -> KbdBacklightInfo | None:
    """Detect keyboard backlight."""
    leds_dir = Path("/sys/class/leds")
    if not leds_dir.exists():
        return None

    for entry in sorted(leds_dir.iterdir()):
        if "kbd" in entry.name.lower() and "backlight" in entry.name.lower():
            try:
                max_br = int((entry / "max_brightness").read_text().strip())
                if max_br > 0:
                    info = KbdBacklightInfo(
                        path=entry, max_brightness=max_br, name=entry.name
                    )
                    log.info(
                        "Detected keyboard backlight: %s (max: %d)",
                        info.name,
                        info.max_brightness,
                    )
                    return info
            except (OSError, IOError, ValueError) as e:
                log.debug("Skipping kbd LED %s: %s", entry.name, e)
                continue

    return None


def _detect_battery() -> BatteryInfo | None:
    """Detect the primary battery."""
    ps_dir = Path("/sys/class/power_supply")
    if not ps_dir.exists():
        return None

    for entry in sorted(ps_dir.iterdir()):
        try:
            ps_type = (entry / "type").read_text().strip()
            if ps_type == "Battery":
                info = BatteryInfo(path=entry, name=entry.name)
                if info.present:
                    log.info("Detected battery: %s", info.name)
                    return info
        except (OSError, IOError) as e:
            log.debug("Skipping power supply %s: %s", entry.name, e)
            continue

    return None


def _detect_wifi() -> WifiInfo | None:
    """Detect the primary Wi-Fi interface."""
    try:
        result = subprocess.run(
            ["iw", "dev"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            for line in result.stdout.splitlines():
                line = line.strip()
                if line.startswith("Interface "):
                    iface = line.split()[1]
                    log.info("Detected Wi-Fi interface: %s", iface)
                    return WifiInfo(interface=iface)
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass

    # Fallback: check /sys/class/net for wireless interfaces
    net_dir = Path("/sys/class/net")
    if net_dir.exists():
        for entry in sorted(net_dir.iterdir()):
            if (entry / "wireless").exists():
                log.info("Detected Wi-Fi interface (sysfs): %s", entry.name)
                return WifiInfo(interface=entry.name)

    return None


def _detect_bluetooth() -> BluetoothInfo | None:
    """Detect bluetooth hardware."""
    try:
        result = subprocess.run(
            ["rfkill", "list", "bluetooth"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0 and result.stdout.strip():
            # Parse rfkill index from output like "0: tpacpi_bluetooth_sw: Bluetooth"
            for line in result.stdout.splitlines():
                if ":" in line and "bluetooth" in line.lower():
                    try:
                        idx = int(line.split(":")[0].strip())
                        log.info("Detected Bluetooth (rfkill index: %d)", idx)
                        return BluetoothInfo(rfkill_index=idx)
                    except ValueError:
                        pass
            # Bluetooth present but couldn't parse index
            log.info("Detected Bluetooth (rfkill index unknown)")
            return BluetoothInfo(rfkill_index=0)
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass

    return None
