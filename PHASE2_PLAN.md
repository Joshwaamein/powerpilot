# Phase 2: Important Fixes

## Issue #5: `profiles.py` — Hardware tweak failures don't affect `success` return

**Problem:** `_apply_hardware_tweaks` returns `None` and logs warnings. `switch_profile` returns `True` even when brightness/wifi/bluetooth tweaks failed. Callers think everything worked.
**Fix:** Make `_apply_hardware_tweaks` return a boolean. Track hardware tweak failures separately — `switch_profile` returns `True` only if backend AND hardware tweaks both succeed.
**Test:** Mock hardware that fails brightness write, verify `switch_profile` returns `False`.

## Issue #11: `inhibitor.py` — Process name matching is too simple

**Problem:** Uses exact match on `ps -eo comm=` output. The `comm` field is truncated to 15 chars by the kernel. A process like `steam-runtime` won't match `steam`. Also `gamemoderun` (11 chars) is fine, but `DaVinci Resolve` wouldn't work.
**Fix:** Switch from `comm` to `args` field, and use substring matching (`if rule_name in process_cmdline`).
**Test:** Mock process list with truncated and full names, verify matching works.

## Issue #13: `hardware.py` — Backlight/kbd writes require root

**Problem:** `BacklightInfo.brightness.setter` writes directly to sysfs, which requires root. On most systems this will fail with `Permission denied`.
**Fix:** Try direct write first. If it fails with PermissionError, fall back to `brightnessctl` CLI tool (commonly available). Log which method is being used.
**Test:** Mock sysfs write failure, verify brightnessctl fallback is attempted.

## Issue #14: `pyproject.toml` — GitHub URLs point to wrong repo

**Problem:** URLs say `powerpilot/powerpilot` but actual repo is `Joshwaamein/powerpilot`.
**Fix:** Update all 3 URLs.
**Test:** N/A (no code test needed).

---

## Test Additions

| Test File | New Tests |
|-----------|-----------|
| `tests/test_profiles.py` | Hardware tweak failure affects return value |
| `tests/test_inhibitor.py` | NEW — Substring matching, truncated names, case sensitivity |
| `tests/test_hardware.py` | NEW — Brightness fallback to brightnessctl |

## Files Changed

| File | Change |
|------|--------|
| `powerpilot/profiles.py` | `_apply_hardware_tweaks` returns bool, integrated into success |
| `powerpilot/inhibitor.py` | Switch to `args` field + substring matching |
| `powerpilot/hardware.py` | Brightness setter falls back to `brightnessctl` |
| `pyproject.toml` | Fix GitHub URLs |
| `tests/test_profiles.py` | Add hardware failure test |
| `tests/test_inhibitor.py` | NEW |
| `tests/test_hardware.py` | NEW |
