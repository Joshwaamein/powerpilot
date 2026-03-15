# Phase 4: PPD ↔ TLP Backend Switcher

## Goal
Add a command and menu option to switch between power-profiles-daemon and TLP backends. This handles the full system-level swap: installing/removing packages, enabling/disabling services, and restarting PowerPilot with the new backend.

## The Problem
Currently, switching between PPD and TLP requires:
1. `sudo apt install tlp` (which auto-removes PPD)
2. `sudo tlp start`
3. Restart PowerPilot

This is error-prone and requires terminal knowledge. PowerPilot should handle this transparently.

## Design

### CLI Command
```bash
powerpilot --switch-backend tlp    # Switch to TLP
powerpilot --switch-backend ppd    # Switch to PPD
```

### Menu Option
Add "Switch to TLP" or "Switch to PPD" at the bottom of the tray menu (above Quit). Shows whichever backend is NOT currently active.

### Switching Flow

**PPD → TLP:**
1. Show confirmation dialog: "Switch to TLP? This removes power-profiles-daemon and installs TLP."
2. Run via polkit helper:
   - `apt install -y tlp tlp-rdw` (auto-removes PPD)
   - `tlp start`
3. Copy default TLP profiles to `~/.config/powerpilot/tlp-profiles/`
4. Restart PowerPilot (exec self)

**TLP → PPD:**
1. Show confirmation dialog: "Switch to PPD? This removes TLP and installs power-profiles-daemon."
2. Run via polkit helper:
   - `apt install -y power-profiles-daemon` (auto-removes TLP)
3. Restart PowerPilot (exec self)

### Safety
- Confirmation dialog before any switch (GTK dialog via polkit)
- Helper script validates packages exist before attempting install
- If install fails, don't restart — show error notification
- Log everything to journald

## Implementation

### New Files
| File | Purpose |
|------|---------|
| `powerpilot/switcher.py` | Backend switching logic |

### Modified Files
| File | Change |
|------|--------|
| `powerpilot/app.py` | Add "Switch backend" menu item + `--switch-backend` CLI flag |
| `data/powerpilot-helper` | Add `switch-backend` command |
| `tests/test_switcher.py` | NEW — Unit tests for switcher logic |

### Helper Script Addition
```bash
# New command in powerpilot-helper:
powerpilot-helper switch-backend <tlp|ppd>
```

This runs with root privileges via pkexec and:
1. Validates the target package is available
2. Installs the target (apt auto-removes the other)
3. Starts the new service
4. Returns success/failure

### switcher.py Design
```python
class BackendSwitcher:
    def can_switch_to(backend: str) -> bool
    def get_current_backend() -> str
    def get_alternative_backend() -> str
    def switch_to(backend: str) -> bool  # Uses pkexec helper
    def restart_app() -> None  # os.execv to restart self
```

### Menu Integration
```
⚡ PowerPilot
  Backend: power-profiles-daemon
  ─────────────────
  🔋 77% (Not charging)
  ─────────────────
  ✓ Power Saver
    Balanced
    Performance
  ─────────────────
    🔄 Switch to TLP          ← NEW
  ─────────────────
    Quit
```

## Tests
- Test `can_switch_to` with mocked apt
- Test `get_alternative_backend` logic
- Test helper command validation
- Test that switch is refused if target already active
