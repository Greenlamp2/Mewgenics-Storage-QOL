"""
tests/test_utils.py
===================
Unit tests for utility helpers (no external dependencies).
"""

from utils.utils import format_item_name


class TestFormatItemName:
    # ── Basic pass-through / capitalization ───────────────────────────────────

    def test_simple_camel_case_unchanged(self):
        # CamelCase with no underscores: capitalize each part
        assert format_item_name("GlassShard") == "Glassshard"

    def test_all_uppercase_single_word_preserved(self):
        # All-uppercase word stays uppercase
        assert format_item_name("SWORD") == "SWORD"

    def test_underscore_split_capitalizes_parts(self):
        result = format_item_name("glass_shard")
        parts = result.split("_")
        assert parts[0] == "Glass"
        assert parts[1] == "Shard"

    def test_mixed_case_underscore(self):
        result = format_item_name("Iron_Helm")
        assert "Iron" in result
        assert "Helm" in result

    # ── Space → underscore conversion ─────────────────────────────────────────

    def test_space_converted_to_underscore(self):
        result = format_item_name("fire sword")
        assert " " not in result
        assert "_" in result

    # ── DEVICE suffix special case ────────────────────────────────────────────

    def test_uppercase_device_suffix_split(self):
        # e.g. "BOMBDEVICE" → "Bomb_Device"
        result = format_item_name("BOMBDEVICE")
        assert "Bomb" in result
        assert "Device" in result

    def test_device_suffix_requires_uppercase_base(self):
        # "bombdevice" (lowercase) should NOT trigger the special case
        result = format_item_name("bombdevice")
        assert result == "Bombdevice"

    # ── Empty string ──────────────────────────────────────────────────────────

    def test_empty_string(self):
        result = format_item_name("")
        assert result == ""

    # ── Multiple underscores ──────────────────────────────────────────────────

    def test_multiple_underscore_parts(self):
        result = format_item_name("iron_sword_of_fire")
        parts = result.split("_")
        assert all(p == p.capitalize() for p in parts)

    # ── Return type ───────────────────────────────────────────────────────────

    def test_returns_string(self):
        assert isinstance(format_item_name("TestItem"), str)

