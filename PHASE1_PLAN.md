# Phase 1: Critical Bug Fixes + Tests

## Bug #1: `log.py` — import order crash

**Problem:** `import logging.handlers` is at bottom of file. If journald unavailable, `RotatingFileHandler` crashes.
**Fix:** Move `import logging.handlers` to the top with other imports.
**Test:** `test_log.py` — Call `setup_logging()` when journald is unavailable, verify file logging works without crash.

## Bug #2: `app.py` — hardcoded "power-saver" in low battery handler

**Problem:** `_on_low_battery` calls `switch_profile("power-saver")` without checking the profile exists.
**Fix:** Use `config["general"]["battery_profile"]` as fallback, and check `get_profile_info` first.
**Test:** `test_app.py` — Mock a config with renamed power-saver profile, trigger low battery, verify it uses the config value.

## Bug #3: `profiles.py` — active profile set on failure

**Problem:** On failure, `_active_profile` is set but `_user_overridden` is not. UI shows wrong profile.
**Fix:** Only set `_active_profile` on full success. On partial failure, don't update tracking.
**Test:** `test_profiles.py` — Mock a backend that fails `set_profile`, verify `_active_profile` unchanged after failed switch.

## Bug #4: `app.py` — missing `_battery_label` init

**Problem:** `self._battery_label` only set inside `_rebuild_menu` when battery exists. Could crash if referenced elsewhere.
**Fix:** Initialize `self._battery_label = None` in `__init__`.
**Test:** `test_app.py` — Create app with no battery hardware, verify no AttributeError on `_battery_label`.

---

## Test Structure

```
tests/
├── __init__.py
├── conftest.py          # Shared fixtures (mock hardware, mock backend, mock config)
├── test_log.py          # Bug #1 test
├── test_profiles.py     # Bug #3 test  
├── test_config.py       # Config loading/saving/validation tests
└── test_hardware.py     # Hardware detection edge cases
```

**Test approach:** Unit tests with `unittest.mock` — no real hardware needed. Mock sysfs paths, mock subprocess calls, mock DBus.

## Files Changed

| File | Change |
|------|--------|
| `powerpilot/log.py` | Move import to top |
| `powerpilot/app.py` | Fix low battery handler + init `_battery_label` |
| `powerpilot/profiles.py` | Fix active profile tracking on failure |
| `tests/conftest.py` | NEW — shared test fixtures |
| `tests/test_log.py` | NEW — logging tests |
| `tests/test_profiles.py` | NEW — profile switching tests |
| `tests/test_app.py` | NEW — app integration tests |
| `tests/test_config.py` | NEW — config tests |
