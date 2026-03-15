PREFIX ?= /usr/local
LIBDIR ?= $(PREFIX)/lib
BINDIR ?= $(PREFIX)/bin
DATADIR ?= $(PREFIX)/share
POLKIT_DIR ?= /usr/share/polkit-1/actions

.PHONY: install uninstall dev-install dev-uninstall lint test clean

install:
	@echo "Installing PowerPilot..."
	# Install Python package
	pip install --break-system-packages .
	# Install helper script
	install -Dm755 data/powerpilot-helper $(DESTDIR)$(LIBDIR)/powerpilot/powerpilot-helper
	# Install polkit policy
	install -Dm644 data/com.github.powerpilot.policy $(DESTDIR)$(POLKIT_DIR)/com.github.powerpilot.policy
	# Install desktop file (autostart)
	install -Dm644 data/powerpilot.desktop $(DESTDIR)$(DATADIR)/applications/powerpilot.desktop
	install -Dm644 data/powerpilot.desktop $(HOME)/.config/autostart/powerpilot.desktop
	# Install TLP profiles
	install -d $(DESTDIR)$(DATADIR)/powerpilot/tlp-profiles
	install -Dm644 tlp-profiles/*.conf $(DESTDIR)$(DATADIR)/powerpilot/tlp-profiles/
	@echo "✓ PowerPilot installed successfully!"
	@echo "  Run 'powerpilot' to start, or log out and back in for autostart."

uninstall:
	@echo "Uninstalling PowerPilot..."
	pip uninstall -y powerpilot 2>/dev/null || true
	rm -f $(DESTDIR)$(LIBDIR)/powerpilot/powerpilot-helper
	rm -f $(DESTDIR)$(POLKIT_DIR)/com.github.powerpilot.policy
	rm -f $(DESTDIR)$(DATADIR)/applications/powerpilot.desktop
	rm -f $(HOME)/.config/autostart/powerpilot.desktop
	rm -rf $(DESTDIR)$(DATADIR)/powerpilot
	@echo "✓ PowerPilot uninstalled."

dev-install:
	@echo "Installing PowerPilot in development mode..."
	pip install --break-system-packages -e .
	chmod +x data/powerpilot-helper
	@echo "✓ Dev install complete. Run: powerpilot"
	@echo "  Helper script is at: $(shell pwd)/data/powerpilot-helper"

dev-uninstall:
	pip uninstall -y powerpilot 2>/dev/null || true

lint:
	python3 -m py_compile powerpilot/__init__.py
	python3 -m py_compile powerpilot/app.py
	python3 -m py_compile powerpilot/config.py
	python3 -m py_compile powerpilot/hardware.py
	python3 -m py_compile powerpilot/profiles.py
	python3 -m py_compile powerpilot/battery.py
	python3 -m py_compile powerpilot/notifications.py
	python3 -m py_compile powerpilot/inhibitor.py
	python3 -m py_compile powerpilot/log.py
	python3 -m py_compile powerpilot/backends/__init__.py
	python3 -m py_compile powerpilot/backends/base.py
	python3 -m py_compile powerpilot/backends/ppd.py
	python3 -m py_compile powerpilot/backends/tlp.py
	@echo "✓ All files compile successfully"

test:
	python3 -m pytest tests/ -v

clean:
	rm -rf build/ dist/ *.egg-info
	find . -name __pycache__ -type d -exec rm -rf {} + 2>/dev/null || true
	find . -name "*.pyc" -delete 2>/dev/null || true
