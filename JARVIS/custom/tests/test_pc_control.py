"""Tests for Maya AI PC control tools."""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from custom.tools.pc_control import (
    list_apps,
    read_file,
    is_app_running,
)


def test_list_apps():
    """List running apps (may be empty on some systems)."""
    apps = list_apps()
    assert isinstance(apps, list), f"Expected list, got {type(apps)}"


def test_read_file():
    """Read the config file itself."""
    # Read the settings.yaml from the MAYA AI config
    from custom.config import MAYA_AI_CONFIG
    content = read_file(str(MAYA_AI_CONFIG))
    assert isinstance(content, str), f"Expected string, got {type(content)}"


def test_is_app_running():
    """Check running apps (False if psutil not available)."""
    result = is_app_running("notepad")
    assert isinstance(result, bool), f"Expected bool, got {type(result)}"


def test_convenience_functions():
    """Test that convenience functions work."""
    from custom.tools.pc_control import list_apps as la
    apps = la()
    assert isinstance(apps, list)


if __name__ == "__main__":
    test_list_apps()
    print("✓ test_list_apps passed")
    test_read_file()
    print("✓ test_read_file passed")
    test_is_app_running()
    print("✓ test_is_app_running passed")
    test_convenience_functions()
    print("✓ test_convenience_functions passed")
    print("\nAll PC control tests passed!")