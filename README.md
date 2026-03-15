# ⚡ PowerPilot

**A universal power profile manager for Linux.**

PowerPilot sits in your system tray and gives you one-click switching between power profiles — combining the deep power management of TLP with the simplicity of a GUI.

![License](https://img.shields.io/badge/license-GPL--3.0-blue)
![Python](https://img.shields.io/badge/python-3.11+-green)
![Desktop](https://img.shields.io/badge/desktop-GNOME-orange)

## Features

- 🔋 **One-click profile switching** from the system tray
- 🔌 **Dual backend support** — works with both `power-profiles-daemon` (PPD) and TLP
- 🔍 **Auto-detects** your active power daemon (TLP > PPD > sysfs fallback)
- 🖥️ **Hardware-aware** — auto-detects screen backlight, keyboard backlight, bluetooth, Wi-Fi
- ⚡ **Auto-switches** profiles when plugging/unplugging AC power
- 🪫 **Low battery protection** — automatically switches to Power Saver at configurable threshold
- 🎮 **App inhibitor** — forces Performance mode when gaming apps are detected (Steam, etc.)
- 🔔 **Desktop notifications** on profile changes
- 📊 **Battery info** in the tray menu (charge %, power draw, time remaining)
- ⚙️ **Fully configurable** via TOML config file
- 📝 **Logs to journald** for easy debugging

## Profiles

| Profile | Description | Backend: PPD | Backend: TLP |
|---------|-------------|-------------|-------------|
| 🔋 **Power Saver** | Max battery life | `power-saver` + tweaks | Aggressive power saving config |
| ⚖️ **Balanced** | Daily driver | `balanced` + tweaks | Moderate config |
| 🚀 **Performance** | Gaming / AI | `performance` + tweaks | Max performance config |
| 🔧 **TLP Auto** | Hands-off | *(TLP only)* | TLP manages everything |

Each profile also controls: screen brightness, keyboard backlight, Wi-Fi power save, and Bluetooth.

## Requirements

- **Python 3.11+**
- **GNOME** desktop (or any DE with AppIndicator support)
- **One of:**
  - `power-profiles-daemon` (default on Ubuntu/Fedora)
  - `tlp` (for advanced power management)
- **System packages:**
  ```
  gir1.2-ayatanaappindicator3-0.1  # System tray support
  gir1.2-notify-0.7                 # Desktop notifications
  ```

## Installation

### Quick Install (Ubuntu/Fedora/Arch)

```bash
# Install system dependencies
sudo apt install gir1.2-ayatanaappindicator3-0.1 gir1.2-notify-0.7

# Clone and install
git clone https://github.com/powerpilot/powerpilot.git
cd powerpilot
sudo make install
```

### Development Install

```bash
git clone https://github.com/powerpilot/powerpilot.git
cd powerpilot
make dev-install
powerpilot  # Run directly
```

### Uninstall

```bash
sudo make uninstall
```

## Configuration

Config file is at `~/.config/powerpilot/config.toml` (auto-created on first run).

```toml
[general]
backend = "auto"              # "auto", "tlp", "ppd", "sysfs"
show_notifications = true
show_battery_info = true
auto_power_saver = true       # Auto power-saver on low battery
low_battery_threshold = 20    # Percentage
auto_switch_on_ac = true      # Auto-switch when plugging/unplugging
ac_profile = "balanced"       # Profile when on AC
battery_profile = "power-saver"  # Profile when on battery

[profiles.power-saver]
label = "Power Saver"
icon = "battery-caution-symbolic"
power_profile = "power-saver"
screen_brightness_percent = 30
keyboard_backlight = 0
wifi_power_save = true
bluetooth = false

[profiles.balanced]
label = "Balanced"
icon = "battery-good-symbolic"
power_profile = "balanced"
screen_brightness_percent = 50
keyboard_backlight = 1
wifi_power_save = false
bluetooth = false

[profiles.performance]
label = "Performance"
icon = "battery-full-charged-symbolic"
power_profile = "performance"
screen_brightness_percent = 75
keyboard_backlight = 2
wifi_power_save = false
bluetooth = true

[profiles.tlp-auto]
label = "TLP Auto"
icon = "preferences-system-symbolic"
tlp_auto = true
requires_tlp = true

[inhibit]
enabled = false
[inhibit.apps]
steam = "performance"
gamemoderun = "performance"
```

## How It Works

### Backend Detection

PowerPilot auto-detects which power management service is active:

1. **TLP** — Checks if `tlp` systemd service is active/enabled
2. **PPD** — Checks if `power-profiles-daemon` is active
3. **sysfs** — Fallback (hardware tweaks only, no profile switching)

### TLP Profile Switching

When using TLP, PowerPilot manages profiles via a symlink at `/etc/tlp.d/99-powerpilot.conf`. This is a clean approach that:
- Never modifies `/etc/tlp.conf` (your base config stays untouched)
- Uses polkit for privilege escalation (GUI password prompt)
- Runs `tlp start` after each switch to apply changes

### PPD Profile Switching

When using power-profiles-daemon, PowerPilot communicates via DBus (no root needed) and adds hardware tweaks on top.

### Battery Monitoring

PowerPilot listens to UPower DBus signals for real-time power source changes. Falls back to polling `/sys/class/power_supply/` if DBus is unavailable.

## Logging

PowerPilot logs to the systemd journal:

```bash
journalctl --user -t powerpilot -f
```

Or check `~/.local/state/powerpilot/powerpilot.log` if journald is unavailable.

## Contributing

Contributions welcome! Please open an issue or PR.

## License

GPL-3.0-or-later. See [LICENSE](LICENSE).
