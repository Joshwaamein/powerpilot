# Phase 3: Improvements (v0.2 scope)

## Improvement #12: `app.py` — Menu rebuilt from scratch every 30 seconds

**Problem:** `_refresh_battery_label` calls `_rebuild_menu()` which destroys and recreates the entire GTK menu every 30s. This is wasteful and can cause UI flicker.
**Fix:** Only update the battery label text and tray icon — don't rebuild the full menu. Rebuild only when profile changes.
**Test:** Verify battery refresh doesn't call `_rebuild_menu`.

## Improvement #15: Add `--version` and `--debug` CLI flags

**Problem:** No way to pass arguments to `powerpilot` command. Users can't enable debug logging or check version without editing config.
**Fix:** Add `argparse` with `--version`, `--debug`, and `--no-notify` flags.
**Test:** Test CLI argument parsing.

## Improvement #16: Config file versioning

**Problem:** If we change the default config structure in future releases, existing user configs won't get new fields. No way to migrate.
**Fix:** Add `config_version = 1` to config. On load, check version and auto-merge new defaults while preserving user customizations.
**Test:** Test config migration with old version.

## Issue #9: `app.py` — `_quit()` return value for GLib signal handler

**Problem:** `_quit` returns `None` instead of `False` for GLib signal handler.
**Fix:** Return `False` explicitly.
**Test:** N/A (trivial fix).

## Issue #10: `tlp.py` — Improve helper discovery

**Problem:** `_find_helper` path resolution is fragile in dev mode.
**Fix:** Also check the `data/` directory relative to the installed package location, and add an environment variable override `POWERPILOT_HELPER_PATH`.
**Test:** Test helper discovery with env var.

---

## Files Changed

| File | Change |
|------|--------|
| `powerpilot/app.py` | Efficient battery refresh, quit return, CLI args |
| `powerpilot/config.py` | Config versioning |
| `powerpilot/backends/tlp.py` | Better helper discovery |
| `tests/test_app.py` | NEW — CLI args test |
| `tests/test_config.py` | Config migration test |
