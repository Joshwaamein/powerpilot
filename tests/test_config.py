"""Tests for powerpilot.config."""

import os
import tempfile
import pytest
from unittest.mock import patch

from powerpilot.config import (
    DEFAULT_CONFIG,
    load_config,
    save_config,
    validate_config,
    get_profile_names,
    _deep_merge,
    _toml_value,
)


class TestConfigValidation:
    """Test config validation."""

    def test_default_config_is_valid(self):
        """Default config should pass validation with no warnings."""
        warnings = validate_config(DEFAULT_CONFIG)
        assert len(warnings) == 0

    def test_invalid_backend(self):
        """Invalid backend value should produce a warning."""
        config = {"general": {"backend": "invalid"}, "profiles": {}}
        warnings = validate_config(config)
        assert any("backend" in w for w in warnings)

    def test_invalid_brightness(self):
        """Brightness outside 0-100 should produce a warning."""
        config = {
            "general": {},
            "profiles": {
                "test": {
                    "label": "Test",
                    "screen_brightness_percent": 150,
                },
            },
        }
        warnings = validate_config(config)
        assert any("brightness" in w for w in warnings)

    def test_missing_label(self):
        """Profile without label should produce a warning."""
        config = {
            "general": {},
            "profiles": {
                "test": {"power_profile": "balanced"},
            },
        }
        warnings = validate_config(config)
        assert any("label" in w for w in warnings)

    def test_invalid_threshold(self):
        """Threshold outside 5-50 should produce a warning."""
        config = {
            "general": {"low_battery_threshold": 100},
            "profiles": {},
        }
        warnings = validate_config(config)
        assert any("threshold" in w for w in warnings)


class TestProfileNames:
    """Test profile name filtering."""

    def test_ppd_hides_tlp_profiles(self):
        """TLP-only profiles should be hidden when TLP is not available."""
        names = get_profile_names(DEFAULT_CONFIG, tlp_available=False)
        assert "tlp-auto" not in names
        assert "power-saver" in names

    def test_tlp_shows_all_profiles(self):
        """All profiles should be visible when TLP is available."""
        names = get_profile_names(DEFAULT_CONFIG, tlp_available=True)
        assert "tlp-auto" in names
        assert "power-saver" in names


class TestConfigIO:
    """Test config save/load."""

    def test_save_and_load(self):
        """Saving and loading config should roundtrip."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_dir = os.path.join(tmpdir, "powerpilot")
            config_path = os.path.join(config_dir, "config.toml")

            with patch("powerpilot.config.get_config_dir", return_value=type(os.path)(config_dir)):
                with patch("powerpilot.config.get_config_path", return_value=type(os.path)(config_path)):
                    from pathlib import Path
                    with patch("powerpilot.config.get_config_dir", return_value=Path(config_dir)):
                        with patch("powerpilot.config.get_config_path", return_value=Path(config_path)):
                            save_config(DEFAULT_CONFIG)
                            assert os.path.exists(config_path)

                            loaded = load_config()
                            # Check key fields survived the roundtrip
                            assert loaded["general"]["backend"] == "auto"
                            assert "power-saver" in loaded["profiles"]
                            assert loaded["profiles"]["balanced"]["label"] == "Balanced"


class TestDeepMerge:
    """Test the deep merge utility."""

    def test_simple_override(self):
        """Override values should take precedence."""
        base = {"a": 1, "b": 2}
        override = {"b": 3}
        result = _deep_merge(base, override)
        assert result == {"a": 1, "b": 3}

    def test_nested_merge(self):
        """Nested dicts should be merged, not replaced."""
        base = {"general": {"a": 1, "b": 2}}
        override = {"general": {"b": 3, "c": 4}}
        result = _deep_merge(base, override)
        assert result["general"] == {"a": 1, "b": 3, "c": 4}

    def test_new_keys_added(self):
        """New keys from override should be added."""
        base = {"a": 1}
        override = {"b": 2}
        result = _deep_merge(base, override)
        assert result == {"a": 1, "b": 2}


class TestTomlValue:
    """Test TOML value serialization."""

    def test_bool(self):
        assert _toml_value(True) == "true"
        assert _toml_value(False) == "false"

    def test_int(self):
        assert _toml_value(42) == "42"

    def test_string(self):
        assert _toml_value("hello") == '"hello"'

    def test_list(self):
        assert _toml_value([1, 2, 3]) == "[1, 2, 3]"
