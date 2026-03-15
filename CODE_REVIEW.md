# 🔍 PowerPilot Code Review — Bugs & Improvements

## 🔴 BUGS (will crash or produce wrong results)

### 1. `log.py` — `logging.handlers` import order bug
`RotatingFileHandler` is used in `setup_logging()` but `import logging.handlers` is at the bottom of the file. If journald is unavailable, this will crash with `AttributeError: module 'logging' has no attribute 'handlers'`.
**Fix:** Move the import to the top of the file.

### 2. `app.py` — `_on_low_battery` hardcodes `"power-saver"` without checking it exists
If the user renamed or removed the `power-saver` profile from their config, this fails silently. Should check `get_profile_info` first, like `_on_power_change` does.

### 3. `profiles.py` — `_active_profile` set even on failure
When `switch_profile` fails, it still sets `self._active_profile = name` but does NOT set `self._user_overridden`. This means the UI shows the wrong active profile and auto-switching isn't properly inhibited after a failed manual switch.

### 4. `app.py` — `_battery_label` attribute only exists if battery detected
If something references `self._battery_label` when no battery is present, it'll crash with `AttributeError`. Should initialize to `None` in `__init__`.

---

## 🟡 ISSUES (fragile or wrong behavior)

### 5. `profiles.py` — Hardware tweak failures don't affect `success` return
`_apply_hardware_tweaks` returns `None` and logs warnings, but `switch_profile` returns `True` even when brightness/wifi/bluetooth tweaks failed. Misleading for callers.

### 6. `battery.py` — Thread safety for callbacks
Battery callbacks are invoked from a background thread but call `GLib.idle_add` in `app.py`. This works for GLib but the `_on_ac` state variable and callback lists have no locking — potential race condition.

### 7. `ppd.py` — DBus connection failure is silent
If DBus init fails, it falls back to CLI. But if both fail, the user gets no feedback about why profiles aren't switching.

### 8. `config.py` — TOML serializer doesn't handle all edge cases
The custom `_dict_to_toml` can produce invalid TOML for deeply nested structures or keys with special characters. Works fine for our config structure, but fragile for user customization.

### 9. `app.py` — `_quit()` return value for GLib signal handler
`GLib.unix_signal_add` expects the callback to return `False` to stop. `_quit` returns `None` which works by accident, but if `Gtk.main_quit()` throws, the signal handler is silently removed.

### 10. `tlp.py` — `_find_helper` won't find the helper in dev mode reliably
Uses `Path(__file__).parent.parent.parent / "data" / "powerpilot-helper"` which assumes a specific directory structure. Works for dev install but may break in edge cases.

### 11. `inhibitor.py` — Process name matching is too simple
Uses exact match on `comm` field (15-char truncated by `ps`). A process named `steam-runtime` might not match `steam`. Should use substring or regex matching.

---

## 🟢 IMPROVEMENTS (better code quality)

### 12. `app.py` — Menu rebuilt from scratch every 30 seconds
`_refresh_battery_label` calls `_rebuild_menu()` which destroys and recreates the entire GTK menu. Should just update the battery label text instead for efficiency.

### 13. `hardware.py` — Backlight/kbd writes require root
`brightness.setter` tries to write directly to sysfs which requires root. Should fall back to the helper script for privileged writes, or use `brightnessctl` if available.

### 14. `pyproject.toml` — GitHub URLs point to wrong repo
URLs say `powerpilot/powerpilot` but should be `Joshwaamein/powerpilot` to match the actual GitHub repo.

### 15. Add `--version` and `--debug` CLI flags
Currently no way to pass arguments to the `powerpilot` command. `argparse` would be a quick addition for `--version`, `--debug`, and `--no-notify` flags.

### 16. `config.py` — No config file migration/versioning
If we change the default config structure in future releases, existing user configs won't get new fields. Should track a config version number.

---

## 📋 Recommended Priority

**Phase 1 (Critical):** Fix bugs #1-4
**Phase 2 (Important):** Fix issues #5, #11, #13, #14
**Phase 3 (v0.2):** Improvements #12, #15, #16 + remaining issues
