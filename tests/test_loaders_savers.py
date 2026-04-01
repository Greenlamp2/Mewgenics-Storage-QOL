"""
tests/test_loaders_savers.py
============================
Tests for loaders and savers against a temporary SQLite save file.
"""
import sqlite3

from tests.helpers import build_blob, make_raw


# ─── load_gold / save_gold ────────────────────────────────────────────────────

class TestGold:
    def test_load_gold_returns_correct_value(self, tmp_save):
        from utils.loaders import load_gold
        assert load_gold(tmp_save) == 100

    def test_load_gold_missing_key_returns_zero(self, tmp_path):
        db = str(tmp_path / "no_gold.sav")
        conn = sqlite3.connect(db)
        conn.execute("CREATE TABLE properties (key TEXT PRIMARY KEY, data)")
        conn.commit()
        conn.close()
        from utils.loaders import load_gold
        assert load_gold(db) == 0

    def test_save_gold_persists(self, tmp_save):
        from utils.loaders import load_gold
        from utils.savers import save_gold
        save_gold(tmp_save, 9999)
        assert load_gold(tmp_save) == 9999

    def test_save_and_load_round_trip(self, tmp_save):
        from utils.loaders import load_gold
        from utils.savers import save_gold
        for amount in [0, 1, 500, 99999]:
            save_gold(tmp_save, amount)
            assert load_gold(tmp_save) == amount


# ─── load_tokens / save_tokens ────────────────────────────────────────────────

class TestTokens:
    def test_load_tokens_initial_values(self, tmp_save):
        from utils.loaders import load_tokens
        tokens = load_tokens(tmp_save)
        assert tokens["common"]    == 5
        assert tokens["uncommon"]  == 3
        assert tokens["rare"]      == 1
        assert tokens["very_rare"] == 0

    def test_all_rarities_present(self, tmp_save):
        from utils.loaders import load_tokens
        tokens = load_tokens(tmp_save)
        for rarity in ("common", "uncommon", "rare", "very_rare"):
            assert rarity in tokens

    def test_save_tokens_round_trip(self, tmp_save):
        from utils.loaders import load_tokens
        from utils.savers import save_tokens
        new = {"common": 10, "uncommon": 20, "rare": 5, "very_rare": 2}
        save_tokens(tmp_save, new)
        loaded = load_tokens(tmp_save)
        assert loaded["common"]    == 10
        assert loaded["uncommon"]  == 20
        assert loaded["rare"]      == 5
        assert loaded["very_rare"] == 2

    def test_missing_db_returns_empty_tokens(self, tmp_path):
        from utils.loaders import load_tokens
        tokens = load_tokens(str(tmp_path / "nonexistent.sav"))
        for rarity in ("common", "uncommon", "rare", "very_rare"):
            assert tokens[rarity] == 0


# ─── load_cats_count ─────────────────────────────────────────────────────────

class TestCatsCount:
    def test_empty_cats_table_returns_zero(self, tmp_save):
        from utils.loaders import load_cats_count
        assert load_cats_count(tmp_save) == 0

    def test_nonexistent_db_returns_zero(self, tmp_path):
        from utils.loaders import load_cats_count
        assert load_cats_count(str(tmp_path / "missing.sav")) == 0


# ─── load_save_properties ────────────────────────────────────────────────────

class TestSaveProperties:
    def test_loads_known_keys(self, tmp_save):
        from utils.loaders import load_save_properties, SAVE_INFO_KEYS
        props = load_save_properties(tmp_save, SAVE_INFO_KEYS)
        assert props["house_gold"]        == "100"
        assert props["current_day"]       == "42"
        assert props["house_food"]        == "50"
        assert props["current_house_weather"] == "Sunny"

    def test_missing_key_returns_empty_string(self, tmp_save):
        from utils.loaders import load_save_properties
        props = load_save_properties(tmp_save, ["nonexistent_key_xyz"])
        assert props["nonexistent_key_xyz"] == ""

    def test_missing_db_returns_empty_dict(self, tmp_path):
        from utils.loaders import load_save_properties, SAVE_INFO_KEYS
        props = load_save_properties(str(tmp_path / "no.sav"), SAVE_INFO_KEYS)
        for k in SAVE_INFO_KEYS:
            assert props[k] == ""


# ─── load_bank_inventory ──────────────────────────────────────────────────────

class TestBankInventory:
    def test_empty_bank_returns_empty_inventory(self, tmp_save):
        from utils.loaders import load_bank_inventory
        inv = load_bank_inventory(tmp_save)
        assert inv.count == 0
        assert inv.raws == []

    def test_nonexistent_db_returns_empty(self, tmp_path):
        from utils.loaders import load_bank_inventory
        inv = load_bank_inventory(str(tmp_path / "missing.sav"))
        assert inv.count == 0


# ─── save_bank_inventory ─────────────────────────────────────────────────────

class TestSaveBankInventory:
    def test_save_and_reload_empty_bank(self, tmp_save, mock_item_catalog):
        from parse.inventory import Inventory
        from utils.loaders import load_bank_inventory
        from utils.savers import save_bank_inventory
        empty_inv = Inventory(None)
        save_bank_inventory(tmp_save, empty_inv)
        loaded = load_bank_inventory(tmp_save)
        assert loaded.count == 0

    def test_save_and_reload_with_item(self, tmp_save, mock_item_catalog):
        from parse.inventory import Inventory
        from utils.loaders import load_bank_inventory
        from utils.savers import save_bank_inventory, build_inventory_blob
        raw = make_raw(name="BankSword", seq_id=1)
        blob = build_inventory_blob([raw])
        inv  = Inventory(blob)
        save_bank_inventory(tmp_save, inv)
        loaded = load_bank_inventory(tmp_save)
        assert loaded.count == 1
        assert loaded.raws[0]["name"] == "BankSword"


# ─── load/save newborn kills ──────────────────────────────────────────────────

class TestNewbornKills:
    def test_initial_kills_zero(self, tmp_save):
        from utils.loaders import load_newborn_kills
        assert load_newborn_kills(tmp_save) == 0

    def test_save_and_load_round_trip(self, tmp_save):
        from utils.loaders import load_newborn_kills
        from utils.savers import save_newborn_kills
        save_newborn_kills(tmp_save, 17)
        assert load_newborn_kills(tmp_save) == 17

    def test_overwrite_persists(self, tmp_save):
        from utils.loaders import load_newborn_kills
        from utils.savers import save_newborn_kills
        save_newborn_kills(tmp_save, 5)
        save_newborn_kills(tmp_save, 99)
        assert load_newborn_kills(tmp_save) == 99


# ─── load/save cat tags ───────────────────────────────────────────────────────

class TestCatTags:
    def test_initial_cat_tags_empty(self, tmp_save):
        from utils.loaders import load_cat_tags
        assert load_cat_tags(tmp_save) == {}

    def test_save_and_load_tags(self, tmp_save):
        from utils.loaders import load_cat_tags
        from utils.savers import save_cat_tags
        tags = {1: ["breeder", "keeper"], 2: ["sell"]}
        save_cat_tags(tmp_save, tags)
        loaded = load_cat_tags(tmp_save)
        assert loaded[1] == ["breeder", "keeper"]
        assert loaded[2] == ["sell"]

    def test_keys_are_ints_after_load(self, tmp_save):
        from utils.loaders import load_cat_tags
        from utils.savers import save_cat_tags
        save_cat_tags(tmp_save, {42: ["tag1"]})
        loaded = load_cat_tags(tmp_save)
        assert 42 in loaded
        assert isinstance(list(loaded.keys())[0], int)

    def test_empty_tag_list_not_stored(self, tmp_save):
        from utils.loaders import load_cat_tags
        from utils.savers import save_cat_tags
        save_cat_tags(tmp_save, {1: [], 2: ["keep"]})
        loaded = load_cat_tags(tmp_save)
        assert 1 not in loaded
        assert loaded[2] == ["keep"]


# ─── load/save bank folders ───────────────────────────────────────────────────

class TestBankFolders:
    def test_initial_folders_empty(self, tmp_save):
        from utils.loaders import load_bank_folders
        folders = load_bank_folders(tmp_save)
        assert folders["folders"] == []
        assert folders["item_folders"] == {}

    def test_save_and_load_round_trip(self, tmp_save):
        from utils.loaders import load_bank_folders
        from utils.savers import save_bank_folders
        data = {
            "folders": [{"id": "abc", "name": "Swords", "parent_id": None}],
            "item_folders": {"1": "abc", "2": None},
        }
        save_bank_folders(tmp_save, data)
        loaded = load_bank_folders(tmp_save)
        assert loaded["folders"][0]["name"] == "Swords"
        assert loaded["item_folders"]["1"] == "abc"


# ─── load/save inventories ────────────────────────────────────────────────────

class TestSaveInventories:
    def test_save_empty_inventories(self, tmp_save, mock_item_catalog):
        from parse.inventory import Inventory
        from utils.loaders import load_inventories
        from utils.savers import save_inventories
        inv = load_inventories(tmp_save)
        save_inventories(tmp_save, inv)  # should not raise

    def test_save_and_reload_with_item(self, tmp_save, mock_item_catalog):
        from parse.inventory import Inventory
        from utils.loaders import load_inventories
        from utils.savers import save_inventories, build_inventory_blob
        # Build storage with one item
        raw  = make_raw(name="Spear", seq_id=1)
        blob = build_inventory_blob([raw])
        inv = load_inventories(tmp_save)
        inv["storage"] = Inventory(blob)
        save_inventories(tmp_save, inv)

        reloaded = load_inventories(tmp_save)
        assert reloaded["storage"].count == 1
        assert reloaded["storage"].raws[0]["name"] == "Spear"


# ─── items pool helpers ───────────────────────────────────────────────────────

class TestItemPoolHelpers:
    def test_add_item_to_pool_new_item(self, tmp_items_pool):
        from utils.savers import add_item_to_pool
        raw = make_raw(name="NewSword")
        result = add_item_to_pool(raw)
        assert result is True

    def test_add_item_to_pool_duplicate_returns_false(self, tmp_items_pool):
        from utils.savers import add_item_to_pool
        raw = make_raw(name="DuplicateItem")
        add_item_to_pool(raw)
        result = add_item_to_pool(raw)
        assert result is False

    def test_remove_from_pool_existing(self, tmp_items_pool):
        from utils.savers import add_item_to_pool, remove_from_pool
        raw = make_raw(name="ToRemove")
        add_item_to_pool(raw)
        result = remove_from_pool("ToRemove")
        assert result is True

    def test_remove_from_pool_nonexistent(self, tmp_items_pool):
        from utils.savers import remove_from_pool
        result = remove_from_pool("DoesNotExist_XYZ")
        assert result is False

