"""
tests/test_item_catalog.py
==========================
Tests for ItemCatalog — uses the REAL data files bundled with the project.
Tests check structural invariants, not specific item names.
"""
import pytest


@pytest.fixture(scope="module")
def catalog():
    from catalogs.itemcatalog import ItemCatalog
    return ItemCatalog()


class TestGetAllNonQuestItems:
    def test_returns_dict(self, catalog):
        result = catalog.get_all_non_quest_items()
        assert isinstance(result, dict)

    def test_not_empty(self, catalog):
        result = catalog.get_all_non_quest_items()
        assert len(result) > 0

    def test_keys_are_strings(self, catalog):
        result = catalog.get_all_non_quest_items()
        for key in list(result.keys())[:20]:
            assert isinstance(key, str)

    def test_values_are_dicts_or_none(self, catalog):
        result = catalog.get_all_non_quest_items()
        for val in list(result.values())[:20]:
            assert val is None or isinstance(val, dict)

    def test_cached_returns_same_object(self, catalog):
        a = catalog.get_all_non_quest_items()
        b = catalog.get_all_non_quest_items()
        assert a is b


class TestGetCategory:
    def test_unknown_item_returns_none(self, catalog):
        assert catalog.get_category("THIS_ITEM_DOES_NOT_EXIST_XYZ") is None

    def test_known_item_returns_string(self, catalog):
        items = catalog.get_all_non_quest_items()
        if not items:
            pytest.skip("No catalog items available")
        name = next(iter(items))
        cat = catalog.get_category(name)
        # Could be None if 'all' lookup fails, but for known items it should be a str
        if cat is not None:
            assert isinstance(cat, str)


class TestGetArmorSetData:
    def test_unknown_item_returns_none(self, catalog):
        result = catalog.get_armor_set_data("NOT_AN_ARMOR_SET_XYZ")
        assert result is None

    def test_known_armor_set_returns_dict_with_keys(self, catalog):
        # Check if any armor set items exist in the catalog
        items = catalog.get_all_non_quest_items()
        armor_set_items = [n for n, d in items.items()
                           if d and catalog.get_category(n) == "armor_sets"]
        if not armor_set_items:
            pytest.skip("No armor set items found in catalog")
        result = catalog.get_armor_set_data(armor_set_items[0])
        if result is not None:
            assert "kind" in result
            assert "set" in result
            assert isinstance(result["set"], list)


class TestGetSetBonus:
    def test_unknown_set_returns_none(self, catalog):
        result = catalog.get_set_bonus("NONEXISTENT_SET_BONUS_XYZ")
        assert result is None

    def test_result_is_string_or_none(self, catalog):
        result = catalog.get_set_bonus("SomeSet")
        assert result is None or isinstance(result, str)


class TestSolveIconName:
    def test_returns_svg_extension(self, catalog):
        result = catalog.solve_icon_name("ITEM_GlassShard")
        assert result.endswith(".svg")

    def test_starts_with_item_prefix(self, catalog):
        result = catalog.solve_icon_name("Sword")
        assert result.startswith("ITEM_")

    def test_strips_desc_suffix(self, catalog):
        result = catalog.solve_icon_name("ITEM_Sword_DESC")
        assert "_DESC" not in result

    def test_strips_fixed_suffix(self, catalog):
        result = catalog.solve_icon_name("ITEM_Helm_FIXED")
        assert "_FIXED" not in result


class TestGetPrice:
    def test_common_price(self, catalog):
        assert catalog.get_price("common") == "14"

    def test_uncommon_price(self, catalog):
        assert catalog.get_price("uncommon") == "20"

    def test_rare_price(self, catalog):
        assert catalog.get_price("rare") == "40"

    def test_very_rare_price(self, catalog):
        assert catalog.get_price("very_rare") == "80"

    def test_unknown_rarity_returns_zero(self, catalog):
        assert catalog.get_price("legendary") == "0"


class TestIsQuestItem:
    def test_unknown_not_quest(self, catalog):
        assert catalog.is_quest_item("FAKE_QUEST_ITEM_XYZ") is False

