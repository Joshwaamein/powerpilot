"""Configuration management for PowerPilot.

Loads, validates, and manages TOML configuration with sensible defaults.
"""

import logging
import os
from copy import deepcopy
from dataclasses import dataclass, field
from pathlib import Path

log = logging.getLogger("powerpilot.config")

# Try stdlib tomllib (Python 3.11+), fall back to tomli
try:
    import tomllib
except ImportError:
    try:
        import tomli as tomllib  # type: ignore[no-redefine]
    except ImportError:
        tomllib = None  # type: ignore[assignment]

# For writing TOML we need a simple serializer (stdlib doesn't have one)
# We'll write a minimal one rather than adding a dependency


DEFAULT_CONFIG = {
    "general": {
        "backend": "auto",  # "auto", "tlp", "ppd", "sysfs"
        "show_notifications": True,
        "show_battery_info": True,
        "auto_power_saver": True,
        "low_battery_threshold": 20,
        "auto_switch_on_ac": True,
        "ac_profile": "balanced",
        "battery_profile": "power-saver",
        "debug": False,
    },
    "profiles": {
        "power-saver": {
            "label": "Power Saver",
            "icon": "battery-caution-symbolic",
            "power_profile": "power-saver",
            "screen_brightness_percent": 30,
            "keyboard_backlight": 0,
            "wifi_power_save": True,
            "bluetooth": False,
        },
        "balanced": {
            "label": "Balanced",
            "icon": "battery-good-symbolic",
            "power_profile": "balanced",
            "screen_brightness_percent": 50,
            "keyboard_backlight": 1,
            "wifi_power_save": False,
            "bluetooth": False,
        },
        "performance": {
            "label": "Performance",
            "icon": "battery-full-charged-symbolic",
            "power_profile": "performance",
            "screen_brightness_percent": 75,
            "keyboard_backlight": 2,
            "wifi_power_save": False,
            "bluetooth": True,
        },
        "tlp-auto": {
            "label": "TLP Auto",
            "icon": "preferences-system-symbolic",
            "tlp_auto": True,
            "requires_tlp": True,
        },
    },
    "inhibit": {
        "enabled": False,
        "apps": {
            "steam": "performance",
            "gamemoderun": "performance",
        },
    },
}


def get_config_dir() -> Path:
    """Get the PowerPilot configuration directory."""
    xdg_config = os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")
    return Path(xdg_config) / "powerpilot"


def get_config_path() -> Path:
    """Get the path to the main config file."""
    return get_config_dir() / "config.toml"


def load_config() -> dict:
    """Load configuration from file, creating defaults if needed.

    Returns:
        Merged configuration dictionary.
    """
    config_path = get_config_path()

    if not config_path.exists():
        log.info("No config file found, creating defaults at %s", config_path)
        config = deepcopy(DEFAULT_CONFIG)
        save_config(config)
        return config

    if tomllib is None:
        log.warning("No TOML parser available, using defaults")
        return deepcopy(DEFAULT_CONFIG)

    try:
        with open(config_path, "rb") as f:
            user_config = tomllib.load(f)
        log.info("Loaded config from %s", config_path)
    except Exception as e:
        log.error("Failed to parse config file: %s. Using defaults.", e)
        return deepcopy(DEFAULT_CONFIG)

    # Merge user config with defaults (user overrides defaults)
    config = _deep_merge(deepcopy(DEFAULT_CONFIG), user_config)
    return config


def save_config(config: dict) -> None:
    """Save configuration to TOML file.

    Args:
        config: Configuration dictionary to save.
    """
    config_dir = get_config_dir()
    config_dir.mkdir(parents=True, exist_ok=True)
    config_path = get_config_path()

    try:
        toml_str = _dict_to_toml(config)
        config_path.write_text(toml_str)
        log.info("Saved config to %s", config_path)
    except Exception as e:
        log.error("Failed to save config: %s", e)


def validate_config(config: dict) -> list[str]:
    """Validate configuration and return list of warnings.

    Args:
        config: Configuration dictionary to validate.

    Returns:
        List of warning messages (empty if valid).
    """
    warnings = []

    general = config.get("general", {})

    backend = general.get("backend", "auto")
    if backend not in ("auto", "tlp", "ppd", "sysfs"):
        warnings.append(f"Invalid backend '{backend}', must be: auto, tlp, ppd, sysfs")

    threshold = general.get("low_battery_threshold", 20)
    if not isinstance(threshold, int) or not (5 <= threshold <= 50):
        warnings.append(f"low_battery_threshold should be 5-50, got {threshold}")

    profiles = config.get("profiles", {})
    for name, profile in profiles.items():
        if "label" not in profile:
            warnings.append(f"Profile '{name}' missing 'label'")

        brightness = profile.get("screen_brightness_percent")
        if brightness is not None and not (0 <= brightness <= 100):
            warnings.append(
                f"Profile '{name}': screen_brightness_percent should be 0-100"
            )

        kbd = profile.get("keyboard_backlight")
        if kbd is not None and not isinstance(kbd, int):
            warnings.append(f"Profile '{name}': keyboard_backlight should be integer")

    if warnings:
        for w in warnings:
            log.warning("Config validation: %s", w)

    return warnings


def get_profile_names(config: dict, tlp_available: bool = False) -> list[str]:
    """Get list of available profile names.

    Args:
        config: Configuration dictionary.
        tlp_available: Whether TLP backend is active.

    Returns:
        List of profile names, filtered by availability.
    """
    profiles = config.get("profiles", {})
    names = []
    for name, profile in profiles.items():
        if profile.get("requires_tlp") and not tlp_available:
            continue
        names.append(name)
    return names


def _deep_merge(base: dict, override: dict) -> dict:
    """Deep merge two dictionaries. Override takes precedence."""
    result = base.copy()
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def _dict_to_toml(d: dict, prefix: str = "") -> str:
    """Convert a dictionary to TOML format string.

    Simple TOML serializer that handles the config structure.
    """
    lines = []
    # First pass: simple key-value pairs
    for key, value in d.items():
        if not isinstance(value, dict):
            lines.append(f"{key} = {_toml_value(value)}")

    if lines and prefix:
        # Insert section header before the values
        lines.insert(0, f"[{prefix}]")
    elif lines:
        pass  # Top-level values

    # Second pass: nested sections
    for key, value in d.items():
        if isinstance(value, dict):
            full_key = f"{prefix}.{key}" if prefix else key
            # Check if it's a section with only dict children (needs subsections)
            has_simple = any(not isinstance(v, dict) for v in value.values())
            has_nested = any(isinstance(v, dict) for v in value.values())

            if has_simple:
                lines.append("")
                lines.append(f"[{full_key}]")
                for k, v in value.items():
                    if not isinstance(v, dict):
                        lines.append(f"{k} = {_toml_value(v)}")

            if has_nested:
                for k, v in value.items():
                    if isinstance(v, dict):
                        nested_key = f"{full_key}.{k}"
                        lines.append("")
                        lines.append(f"[{nested_key}]")
                        for nk, nv in v.items():
                            if not isinstance(nv, dict):
                                lines.append(f"{nk} = {_toml_value(nv)}")
                            else:
                                # One more level deep
                                deep_key = f"{nested_key}.{nk}"
                                lines.append("")
                                lines.append(f"[{deep_key}]")
                                for dk, dv in nv.items():
                                    lines.append(f"{dk} = {_toml_value(dv)}")

            if not has_simple and not has_nested:
                lines.append("")
                lines.append(f"[{full_key}]")

    return "\n".join(lines) + "\n"


def _toml_value(value) -> str:
    """Convert a Python value to TOML representation."""
    if isinstance(value, bool):
        return "true" if value else "false"
    elif isinstance(value, int):
        return str(value)
    elif isinstance(value, float):
        return str(value)
    elif isinstance(value, str):
        return f'"{value}"'
    elif isinstance(value, list):
        items = ", ".join(_toml_value(v) for v in value)
        return f"[{items}]"
    else:
        return f'"{value}"'
