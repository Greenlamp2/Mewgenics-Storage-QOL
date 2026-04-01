"""
tests/test_item.py
==================
Unit tests for Item and GhostItem — catalog is mocked so no data files are
required.  Tests focus on flag logic, field assignment, and rarity handling.
"""

from tests.helpers import make_raw, MOCK_ITEM_DETAILS


# ─── Item ─────────────────────────────────────────────────────────────────────

class TestItemFlags:
    """sep_flag / trash logic."""

    def test_not_broken_when_sep_flag_5_in_storage(self, mock_item_catalog):
        from parse.item import Item
        raw = make_raw(sep_flag=5)
        item = Item(raw, trash=False)
        assert item.broken is False

    def test_broken_when_sep_flag_5_in_trash(self, mock_item_catalog):
        from parse.item import Item
        raw = make_raw(sep_flag=5)
        item = Item(raw, trash=True)
        assert item.broken is True

    def test_not_broken_when_sep_flag_1(self, mock_item_catalog):
        from parse.item import Item
        raw = make_raw(sep_flag=1)
        item = Item(raw, trash=True)
        assert item.broken is False

    def test_used_when_sep_flag_3(self, mock_item_catalog):
        from parse.item import Item
        raw = make_raw(sep_flag=3)
        item = Item(raw)
        assert item.used is True

    def test_not_used_when_sep_flag_1(self, mock_item_catalog):
        from parse.item import Item
        raw = make_raw(sep_flag=1)
        item = Item(raw)
        assert item.used is False

    def test_not_used_when_sep_flag_5(self, mock_item_catalog):
        from parse.item import Item
        raw = make_raw(sep_flag=5)
        item = Item(raw)
        assert item.used is False


class TestItemFields:
    """Core field assignment from raw dict."""

    def test_name_assigned(self, mock_item_catalog):
        from parse.item import Item
        raw = make_raw(name="Spear")
        item = Item(raw)
        assert item.name == "Spear"

    def test_subname_assigned(self, mock_item_catalog):
        from parse.item import Item
        raw = make_raw(subname="Sharp")
        item = Item(raw)
        assert item.subname == "Sharp"

    def test_charges_assigned(self, mock_item_catalog):
        from parse.item import Item
        raw = make_raw(charges=3)
        item = Item(raw)
        assert item.charges == 3

    def test_seq_id_assigned(self, mock_item_catalog):
        from parse.item import Item
        raw = make_raw(seq_id=42)
        item = Item(raw)
        assert item.seqId == 42

    def test_category_from_catalog(self, mock_item_catalog):
        from parse.item import Item
        raw = make_raw()
        item = Item(raw)
        assert item.category == "weapons"

    def test_rarity_from_details(self, mock_item_catalog):
        from parse.item import Item
        raw = make_raw()
        item = Item(raw)
        assert item.rarity == "common"

    def test_is_not_armor_set_by_default(self, mock_item_catalog):
        from parse.item import Item
        raw = make_raw()
        item = Item(raw)
        assert item.is_armor_set is False
        assert item.armor_set_name is None


class TestItemRarityNormalization:
    """consumable_X rarity prefix removal."""

    def test_consumable_common_normalized(self, mock_item_catalog):
        from parse.item import Item
        mock_item_catalog.get_item_full.return_value = {
            **MOCK_ITEM_DETAILS, "rarity": "consumable_common"
        }
        raw = make_raw()
        item = Item(raw)
        assert item.rarity == "common"

    def test_consumable_rare_normalized(self, mock_item_catalog):
        from parse.item import Item
        mock_item_catalog.get_item_full.return_value = {
            **MOCK_ITEM_DETAILS, "rarity": "consumable_rare"
        }
        raw = make_raw()
        item = Item(raw)
        assert item.rarity == "rare"

    def test_non_consumable_rarity_unchanged(self, mock_item_catalog):
        from parse.item import Item
        mock_item_catalog.get_item_full.return_value = {
            **MOCK_ITEM_DETAILS, "rarity": "very_rare"
        }
        raw = make_raw()
        item = Item(raw)
        assert item.rarity == "very_rare"

    def test_none_rarity_defaults_to_common(self, mock_item_catalog):
        from parse.item import Item
        mock_item_catalog.get_item_full.return_value = {
            **MOCK_ITEM_DETAILS, "rarity": None
        }
        raw = make_raw()
        item = Item(raw)
        assert item.rarity == "common"


class TestItemArmorSetEnrichment:
    """Armor-set category remapping."""

    def test_armor_set_category_remapped_to_kind(self, mock_item_catalog):
        from parse.item import Item
        mock_item_catalog.get_category.return_value = "armor_sets"
        mock_item_catalog.get_armor_set_data.return_value = {
            "kind": "head",
            "set": ["HelmOfFire", "BootsOfFire"],
            "desc_resolved": "+2 STR",
        }
        raw = make_raw(name="HelmOfFire")
        item = Item(raw)
        assert item.is_armor_set is True
        assert item.category == "head"
        assert item.armor_set_name == ["HelmOfFire", "BootsOfFire"]

    def test_armor_set_with_no_data_keeps_armor_sets_category(self, mock_item_catalog):
        from parse.item import Item
        mock_item_catalog.get_category.return_value = "armor_sets"
        mock_item_catalog.get_armor_set_data.return_value = None
        raw = make_raw(name="MysteriousPiece")
        item = Item(raw)
        assert item.is_armor_set is True
        assert item.category == "armor_sets"


# ─── GhostItem ────────────────────────────────────────────────────────────────

class TestGhostItem:
    def test_locked_true(self, mock_item_catalog):
        from parse.item import GhostItem
        g = GhostItem("UnknownItem", dict(MOCK_ITEM_DETAILS))
        assert g.locked is True

    def test_broken_false(self, mock_item_catalog):
        from parse.item import GhostItem
        g = GhostItem("UnknownItem", dict(MOCK_ITEM_DETAILS))
        assert g.broken is False

    def test_name_assigned(self, mock_item_catalog):
        from parse.item import GhostItem
        g = GhostItem("CoolSword", dict(MOCK_ITEM_DETAILS))
        assert g.name == "CoolSword"

    def test_rarity_from_details(self, mock_item_catalog):
        from parse.item import GhostItem
        g = GhostItem("SomeItem", {**MOCK_ITEM_DETAILS, "rarity": "uncommon"})
        assert g.rarity == "uncommon"

    def test_consumable_rarity_normalized(self, mock_item_catalog):
        from parse.item import GhostItem
        g = GhostItem("Potion", {**MOCK_ITEM_DETAILS, "rarity": "consumable_rare"})
        assert g.rarity == "rare"

    def test_not_quest_item(self, mock_item_catalog):
        from parse.item import GhostItem
        g = GhostItem("SomeItem", dict(MOCK_ITEM_DETAILS))
        assert g.is_quest_item is False

    def test_syringe_icon_override(self, mock_item_catalog):
        from parse.item import GhostItem
        mock_item_catalog.get_category.return_value = "modifiers"
        details = {**MOCK_ITEM_DETAILS, "name_resolved": "IronSyringe"}
        g = GhostItem("IronSyringe", details)
        assert g.icon_name == "../misc/sysinge.png"

    def test_soul_jar_icon_override(self, mock_item_catalog):
        from parse.item import GhostItem
        g = GhostItem("SoulJar", dict(MOCK_ITEM_DETAILS))
        assert g.icon_name == "../misc/soul_jar.png"

