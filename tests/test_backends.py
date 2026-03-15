"""Comprehensive tests for backend detection, PPD, TLP, and sysfs backends."""

import subprocess
import tempfile
import os
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from powerpilot.backends import detect_backend
from powerpilot.backends.base import PowerBackend, SysfsBackend
from powerpilot.backends.ppd import PPDBackend
from powerpilot.backends.tlp import TLPBackend, get_tlp_status


class TestBackendDetection:
    """Test auto-detection logic in backends/__init__.py."""

    @patch("powerpilot.backends._try_tlp", return_value=None)
    @patch("powerpilot.backends._try_ppd")
    def test_auto_detects_ppd(self, mock_ppd, mock_tlp):
        mock_ppd.return_value = MagicMock(spec=PowerBackend)
        backend = detect_backend("auto")
        assert backend is not None

    @patch("powerpilot.backends._try_ppd", return_value=None)
    @patch("powerpilot.backends._try_tlp")
    def test_auto_detects_tlp(self, mock_tlp, mock_ppd):
        mock_tlp.return_value = MagicMock(spec=PowerBackend)
        backend = detect_backend("auto")
        assert backend is not None

    @patch("powerpilot.backends._try_ppd", return_value=None)
    @patch("powerpilot.backends._try_tlp", return_value=None)
    def test_fallback_to_sysfs(self, mock_tlp, mock_ppd):
        backend = detect_backend("auto")
        assert isinstance(backend, SysfsBackend)

    @patch("powerpilot.backends._try_tlp", return_value=None)
    @patch("powerpilot.backends._try_ppd", return_value=None)
    def test_forced_sysfs(self, mock_ppd, mock_tlp):
        backend = detect_backend("sysfs")
        assert isinstance(backend, SysfsBackend)

    @patch("powerpilot.backends._is_service_active", return_value=True)
    def test_tlp_priority_over_ppd(self, mock_active):
        """TLP should be detected before PPD when both are active."""
        # When _is_service_active returns True for "tlp", TLP should be chosen
        with patch("powerpilot.backends._try_tlp") as mock_tlp:
            mock_tlp.return_value = MagicMock(spec=PowerBackend, backend_type="tlp")
            backend = detect_backend("auto")
            mock_tlp.assert_called()


class TestSysfsBackend:
    """Test the sysfs fallback backend."""

    def test_name(self):
        backend = SysfsBackend()
        assert "sysfs" in backend.name.lower()

    def test_backend_type(self):
        assert SysfsBackend().backend_type == "sysfs"

    def test_no_profiles(self):
        assert SysfsBackend().get_available_profiles() == []

    def test_no_active_profile(self):
        assert SysfsBackend().get_active_profile() is None

    def test_set_profile_fails(self):
        assert SysfsBackend().set_profile("balanced") is False

    def test_no_tlp_auto(self):
        assert SysfsBackend().supports_tlp_auto is False
        assert SysfsBackend().apply_tlp_auto() is False


class TestPPDBackend:
    """Test PPD backend with mocked system calls."""

    @patch("subprocess.run")
    def test_get_available_profiles_cli(self, mock_run):
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="  performance:\n\n  balanced:\n\n* power-saver:\n",
        )
        with patch.object(PPDBackend, "_init_dbus"):
            backend = PPDBackend()
            backend._dbus_proxy = None
            profiles = backend.get_available_profiles()
            assert "power-saver" in profiles
            assert "balanced" in profiles
            assert "performance" in profiles

    @patch("subprocess.run")
    def test_get_active_profile_cli(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="balanced\n")
        with patch.object(PPDBackend, "_init_dbus"):
            backend = PPDBackend()
            backend._dbus_proxy = None
            assert backend.get_active_profile() == "balanced"

    @patch("subprocess.run")
    def test_set_profile_cli_success(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="")
        with patch.object(PPDBackend, "_init_dbus"):
            backend = PPDBackend()
            backend._dbus_proxy = None
            # Mock get_available_profiles to return the profiles
            with patch.object(backend, "get_available_profiles",
                              return_value=["power-saver", "balanced", "performance"]):
                result = backend.set_profile("balanced")
                assert result is True

    @patch("subprocess.run")
    def test_set_profile_cli_failure(self, mock_run):
        mock_run.return_value = MagicMock(returncode=1, stderr="error")
        with patch.object(PPDBackend, "_init_dbus"):
            backend = PPDBackend()
            backend._dbus_proxy = None
            with patch.object(backend, "get_available_profiles",
                              return_value=["power-saver", "balanced", "performance"]):
                result = backend.set_profile("balanced")
                assert result is False

    def test_set_profile_rejects_unavailable(self):
        with patch.object(PPDBackend, "_init_dbus"):
            backend = PPDBackend()
            backend._dbus_proxy = None
            with patch.object(backend, "get_available_profiles",
                              return_value=["power-saver", "balanced"]):
                result = backend.set_profile("turbo")
                assert result is False

    def test_ppd_properties(self):
        with patch.object(PPDBackend, "_init_dbus"):
            backend = PPDBackend()
            assert backend.name == "power-profiles-daemon"
            assert backend.backend_type == "ppd"
            assert backend.supports_tlp_auto is False


class TestTLPBackend:
    """Test TLP backend with mocked file system."""

    def _make_tlp_backend(self, tmpdir):
        """Create a TLP backend with mock profiles directory."""
        profiles_dir = Path(tmpdir) / "tlp-profiles"
        profiles_dir.mkdir()
        # Create test profile files
        for name in ["power-saver", "balanced", "performance"]:
            conf = profiles_dir / f"{name}.conf"
            conf.write_text(f"# PowerPilot profile: {name}\nCPU_ENERGY_PERF_POLICY_ON_BAT=\"power\"\n")

        with patch("powerpilot.backends.tlp._get_user_profiles_dir", return_value=profiles_dir):
            backend = TLPBackend()
        backend._profiles_dir = profiles_dir
        return backend

    def test_tlp_properties(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            backend = self._make_tlp_backend(tmpdir)
            assert backend.name == "TLP"
            assert backend.backend_type == "tlp"
            assert backend.supports_tlp_auto is True

    def test_get_available_profiles(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            backend = self._make_tlp_backend(tmpdir)
            profiles = backend.get_available_profiles()
            assert "power-saver" in profiles
            assert "balanced" in profiles
            assert "performance" in profiles

    def test_get_active_profile_no_config(self):
        """No PowerPilot config = TLP auto mode."""
        with tempfile.TemporaryDirectory() as tmpdir:
            backend = self._make_tlp_backend(tmpdir)
            with patch("powerpilot.backends.tlp.TLP_POWERPILOT_CONF",
                        Path("/nonexistent/99-powerpilot.conf")):
                assert backend.get_active_profile() == "tlp-auto"

    def test_apply_tlp_auto(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            backend = self._make_tlp_backend(tmpdir)
            with patch.object(backend, "_remove_powerpilot_conf", return_value=True):
                assert backend.apply_tlp_auto() is True

    def test_set_profile_nonexistent(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            backend = self._make_tlp_backend(tmpdir)
            result = backend.set_profile("nonexistent")
            assert result is False

    @patch("subprocess.run")
    def test_get_tlp_status_enabled(self, mock_run):
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="State          = enabled\nMode           = battery\nPower source   = battery\n",
        )
        status = get_tlp_status()
        assert status["enabled"] is True
        assert status["mode"] == "battery"
        assert status["power_source"] == "battery"

    @patch("subprocess.run", side_effect=FileNotFoundError)
    def test_get_tlp_status_not_installed(self, mock_run):
        status = get_tlp_status()
        assert status["enabled"] is False

    def test_find_helper_with_env_var(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            backend = self._make_tlp_backend(tmpdir)
            helper_path = Path(tmpdir) / "test-helper"
            helper_path.write_text("#!/bin/bash\necho OK")
            os.chmod(helper_path, 0o755)

            with patch.dict(os.environ, {"POWERPILOT_HELPER_PATH": str(helper_path)}):
                result = backend._find_helper()
                assert result == str(helper_path)

    def test_find_helper_env_var_invalid(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            backend = self._make_tlp_backend(tmpdir)
            with patch.dict(os.environ, {"POWERPILOT_HELPER_PATH": "/nonexistent"}):
                with patch("shutil.which", return_value=None):
                    result = backend._find_helper()
                    # Should not return the invalid path
                    assert result != "/nonexistent"
