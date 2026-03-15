"""Shared test fixtures for PowerPilot tests."""

import pytest
from unittest.mock import MagicMock
from copy import deepcopy

from powerpilot.config import DEFAULT_CONFIG
from powerpilot.hardware import HardwareCapabilities, BacklightInfo, KbdBacklightInfo, BatteryInfo, WifiInfo, BluetoothInfo
from powerpilot.backends.base import PowerBackend


class MockBackend(PowerBackend):
    """Mock backend for testing."""

    def __init__(self, profiles=None, active="balanced", fail_set=False):
        self._profiles = profiles or ["power-saver", "balanced", "performance"]
        self._active = active
        self._fail_set = fail_set

    @property
    def name(self) -> str:
        return "mock"

    @property
    def backend_type(self) -> str:
        return "ppd"

    def get_available_profiles(self) -> list[str]:
        return self._profiles

    def get_active_profile(self) -> str | None:
        return self._active

    def set_profile(self, profile: str) -> bool:
        if self._fail_set:
            return False
        self._active = profile
        return True


@pytest.fixture
def default_config():
    """Return a fresh copy of the default config."""
    return deepcopy(DEFAULT_CONFIG)


@pytest.fixture
def mock_backend():
    """Return a mock backend that succeeds."""
    return MockBackend()


@pytest.fixture
def failing_backend():
    """Return a mock backend that fails set_profile."""
    return MockBackend(fail_set=True)


@pytest.fixture
def mock_hardware():
    """Return mock hardware capabilities (no real hardware)."""
    hw = HardwareCapabilities()
    # No real devices — all None
    return hw
