"""
tests/test_app_controller.py
============================
Integration tests for AppController backed by a temporary SQLite save file.
The item catalog is mocked so no real catalog data is required.
"""
import pytest

from tests.helpers import (
    add_item_to_inv, make_raw,
    MOCK_RARE_DETAILS, MOCK_UNCOMMON_DETAILS,
)


# ─── load_data ────────────────────────────────────────────────────────────────

class TestLoadData:
    def test_inventories_loaded(self, controller):
        assert "storage" in controller.inventories
        assert "trash"   in controller.inventories
        assert "bank"    in controller.inventories

    def test_empty_storage_after_load(self, controller):
        assert controller.inventories["storage"].count == 0

    def test_gold_loaded(self, controller):
        assert controller.golds == 100

    def test_tokens_loaded(self, controller):
        assert controller.tokens["common"]    == 5
        assert controller.tokens["uncommon"]  == 3
        assert controller.tokens["rare"]      == 1
        assert controller.tokens["very_rare"] == 0

    def test_save_properties_loaded(self, controller):
        assert controller.save_properties["house_gold"] == "100"
        assert controller.save_properties["current_day"] == "42"

    def test_cats_count_in_properties(self, controller):
        assert "_cats_count" in controller.save_properties
        assert controller.save_properties["_cats_count"] == "0"

    def test_cats_not_loaded_by_load_data(self, controller):
        # Cats are deferred — load_data should not populate self.cats
        assert controller.cats == []

    def test_loaded_mtime_set(self, controller):
        assert controller.loaded_mtime is not None


# ─── sacrifice ────────────────────────────────────────────────────────────────

class TestSacrificeItem:
    def test_sacrifice_removes_item_from_storage(self, controller):
        add_item_to_inv(controller, "storage", "TestItem")
        assert controller.inventories["storage"].count == 1
        controller.apply_sacrifice_item("storage", 0)
        assert controller.inventories["storage"].count == 0

    def test_sacrifice_increments_token(self, controller):
        add_item_to_inv(controller, "storage", "TestItem")
        before = controller.tokens["common"]
        controller.apply_sacrifice_item("storage", 0)
        assert controller.tokens["common"] == before + 1

    def test_sacrifice_persists_token_to_db(self, controller):
        add_item_to_inv(controller, "storage", "TestItem")
        controller.apply_sacrifice_item("storage", 0)
        from utils.loaders import load_tokens
        tokens = load_tokens(controller.sav_path)
        assert tokens["common"] == 6  # was 5 + 1

    def test_sacrifice_trash_item(self, controller):
        add_item_to_inv(controller, "trash", "TestItem")
        controller.apply_sacrifice_item("trash", 0)
        assert controller.inventories["trash"].count == 0

    def test_get_sacrifice_gains(self, controller):
        add_item_to_inv(controller, "storage", "TestItem")
        gains = controller.get_sacrifice_gains("storage", 0)
        assert gains == {"common": 1}


class TestSacrificeMultiple:
    def test_sacrifice_multiple_removes_all(self, controller):
        for i in range(3):
            add_item_to_inv(controller, "storage", "TestItem", seq_id=i + 1)
        controller.apply_sacrifice_multiple([0, 1, 2])
        assert controller.inventories["storage"].count == 0

    def test_sacrifice_multiple_increments_tokens_correctly(self, controller):
        for i in range(3):
            add_item_to_inv(controller, "storage", "TestItem", seq_id=i + 1)
        before = controller.tokens["common"]
        controller.apply_sacrifice_multiple([0, 1, 2])
        assert controller.tokens["common"] == before + 3

    def test_sacrifice_multiple_partial_indices(self, controller):
        for i in range(4):
            add_item_to_inv(controller, "storage", "TestItem", seq_id=i + 1)
        controller.apply_sacrifice_multiple([0, 2])
        assert controller.inventories["storage"].count == 2

    def test_get_sacrifice_multiple_gains(self, controller):
        for i in range(2):
            add_item_to_inv(controller, "storage", "TestItem", seq_id=i + 1)
        gains = controller.get_sacrifice_multiple_gains([0, 1])
        assert gains["common"] == 2


class TestSacrificeAllTrash:
    def test_sacrifice_all_trash_non_broken(self, controller):
        add_item_to_inv(controller, "trash", "TestItem", sep_flag=1)
        add_item_to_inv(controller, "trash", "TestItem", sep_flag=1)
        controller.apply_sacrifice_all_trash()
        assert controller.inventories["trash"].count == 0

    def test_sacrifice_all_trash_keeps_broken_items(self, controller):
        add_item_to_inv(controller, "trash", "TestItem", sep_flag=5)
        add_item_to_inv(controller, "trash", "TestItem", sep_flag=1)
        controller.apply_sacrifice_all_trash()
        # Only broken item should remain
        assert controller.inventories["trash"].count == 1
        assert controller.inventories["trash"].items[0].broken is True

    def test_get_sacrifice_all_trash_gains(self, controller):
        add_item_to_inv(controller, "trash", "TestItem", sep_flag=1)
        add_item_to_inv(controller, "trash", "TestItem", sep_flag=5)  # broken → not counted
        gains = controller.get_sacrifice_all_trash_gains()
        assert gains.get("common", 0) == 1


# ─── move storage ↔ trash ─────────────────────────────────────────────────────

class TestMoveItem:
    def test_storage_to_trash(self, controller):
        add_item_to_inv(controller, "storage", "TestItem")
        controller.apply_move_item("storage", 0)
        assert controller.inventories["storage"].count == 0
        assert controller.inventories["trash"].count   == 1

    def test_trash_to_storage(self, controller):
        add_item_to_inv(controller, "trash", "TestItem")
        controller.apply_move_item("trash", 0)
        assert controller.inventories["trash"].count   == 0
        assert controller.inventories["storage"].count == 1

    def test_move_returns_destination_key(self, controller):
        add_item_to_inv(controller, "storage", "TestItem")
        dest = controller.apply_move_item("storage", 0)
        assert dest == "trash"

    def test_moved_item_name_preserved(self, controller):
        add_item_to_inv(controller, "storage", "SwordOfTesting")
        controller.apply_move_item("storage", 0)
        assert controller.inventories["trash"].raws[0]["name"] == "SwordOfTesting"


class TestMoveMultipleToTrash:
    def test_moves_selected_items(self, controller):
        for i in range(3):
            add_item_to_inv(controller, "storage", "TestItem", seq_id=i + 1)
        controller.apply_move_multiple_to_trash([0, 2])
        assert controller.inventories["storage"].count == 1
        assert controller.inventories["trash"].count   == 2

    def test_remaining_item_is_the_non_selected(self, controller):
        add_item_to_inv(controller, "storage", "Keep",    seq_id=1)
        add_item_to_inv(controller, "storage", "Discard", seq_id=2)
        controller.apply_move_multiple_to_trash([1])
        assert controller.inventories["storage"].raws[0]["name"] == "Keep"


class TestMoveMultipleToStorage:
    def test_moves_from_trash_to_storage(self, controller):
        for i in range(3):
            add_item_to_inv(controller, "trash", "TestItem", seq_id=i + 1)
        controller.apply_move_multiple_to_storage("trash", [0, 1])
        assert controller.inventories["trash"].count   == 1
        assert controller.inventories["storage"].count == 2


# ─── bank ─────────────────────────────────────────────────────────────────────

class TestMoveToBank:
    def test_storage_to_bank(self, controller):
        add_item_to_inv(controller, "storage", "TestItem")
        controller.apply_move_to_bank(0)
        assert controller.inventories["storage"].count == 0
        assert controller.inventories["bank"].count    == 1

    def test_bank_item_name_preserved(self, controller):
        add_item_to_inv(controller, "storage", "GoldenKey")
        controller.apply_move_to_bank(0)
        assert controller.inventories["bank"].raws[0]["name"] == "GoldenKey"

    def test_move_to_bank_auto_discovers_pool(self, controller):
        # Item not yet in pool → should be added
        add_item_to_inv(controller, "storage", "NewDiscovery")
        assert "NewDiscovery" not in controller.items_pool
        controller.apply_move_to_bank(0)
        assert "NewDiscovery" in controller.items_pool


class TestMoveFromBank:
    def test_bank_to_storage(self, controller):
        add_item_to_inv(controller, "bank", "TestItem")
        controller.apply_move_from_bank(0)
        assert controller.inventories["bank"].count    == 0
        assert controller.inventories["storage"].count == 1

    def test_moved_item_name_preserved(self, controller):
        add_item_to_inv(controller, "bank", "AncientRelic")
        controller.apply_move_from_bank(0)
        assert controller.inventories["storage"].raws[0]["name"] == "AncientRelic"


class TestMoveBankToTrash:
    def test_bank_to_trash(self, controller):
        add_item_to_inv(controller, "bank", "TestItem")
        controller.apply_move_bank_item_to_trash(0)
        assert controller.inventories["bank"].count  == 0
        assert controller.inventories["trash"].count == 1

    def test_multiple_bank_to_trash(self, controller):
        for i in range(3):
            add_item_to_inv(controller, "bank", "TestItem", seq_id=i + 1)
        controller.apply_move_multiple_bank_to_trash([0, 1])
        assert controller.inventories["bank"].count  == 1
        assert controller.inventories["trash"].count == 2


# ─── repair ───────────────────────────────────────────────────────────────────

class TestRepairItem:
    def test_repair_moves_item_to_storage(self, controller):
        add_item_to_inv(controller, "trash", "TestItem", sep_flag=5)
        controller.apply_repair_item(0)
        assert controller.inventories["trash"].count   == 0
        assert controller.inventories["storage"].count == 1

    def test_repair_costs_3_tokens(self, controller):
        add_item_to_inv(controller, "trash", "TestItem", sep_flag=5)
        before = controller.tokens["common"]
        controller.apply_repair_item(0)
        assert controller.tokens["common"] == before - 3

    def test_repair_resets_sep_flag(self, controller):
        add_item_to_inv(controller, "trash", "TestItem", sep_flag=5)
        controller.apply_repair_item(0)
        repaired = controller.inventories["storage"].raws[0]
        assert repaired["sep_flag"] == 1

    def test_get_repair_info(self, controller):
        add_item_to_inv(controller, "trash", "TestItem", sep_flag=5)
        info = controller.get_repair_info(0)
        assert info["cost"]       == 3
        assert info["rarity"]     == "common"
        assert info["available"]  == 5
        assert info["can_afford"] is True

    def test_get_repair_info_cannot_afford(self, controller):
        controller.tokens["common"] = 2
        add_item_to_inv(controller, "trash", "TestItem", sep_flag=5)
        info = controller.get_repair_info(0)
        assert info["can_afford"] is False


# ─── pool purchase ────────────────────────────────────────────────────────────

class TestPurchasePoolItem:
    def test_purchase_discovered_item_adds_to_storage(self, controller, mock_item_catalog):
        from parse.item import Item
        # Manually add item to pool
        raw = make_raw(name="TestItem", seq_id=1)
        controller.items_pool["TestItem"] = raw
        controller.pool_items = [Item(raw)]
        controller.inv_items["Pool"] = controller.pool_items

        before = controller.tokens["common"]
        controller.apply_purchase_pool_item(controller.pool_items[0])
        assert controller.inventories["storage"].count == 1
        assert controller.tokens["common"] == before - 2  # PURCHASE_COST = 2

    def test_purchase_ghost_item_discovers_in_pool(self, controller, mock_item_catalog):
        from parse.item import GhostItem
        ghost = GhostItem("RareItem", dict(MOCK_RARE_DETAILS))
        controller.tokens["rare"] = 5

        controller.apply_purchase_pool_item(ghost)
        assert "RareItem" in controller.items_pool
        assert controller.inventories["storage"].count == 1

    def test_purchase_deducts_correct_rarity_tokens(self, controller, mock_item_catalog):
        from parse.item import GhostItem
        ghost = GhostItem("UncommonItem", dict(MOCK_UNCOMMON_DETAILS))
        controller.tokens["uncommon"] = 5
        before = controller.tokens["uncommon"]

        controller.apply_purchase_pool_item(ghost)
        assert controller.tokens["uncommon"] == before - 2

    def test_purchase_raises_if_insufficient_tokens(self, controller, mock_item_catalog):
        from parse.item import GhostItem
        ghost = GhostItem("RareItem", dict(MOCK_RARE_DETAILS))
        controller.tokens["rare"] = 1  # not enough (need 2)
        with pytest.raises(ValueError, match="Not enough tokens"):
            controller.apply_purchase_pool_item(ghost)


# ─── bank folders ─────────────────────────────────────────────────────────────

class TestBankFolders:
    def test_create_folder(self, controller):
        folder_id = controller.create_bank_folder("Swords", None)
        assert folder_id is not None
        folders = controller.get_bank_subfolders(None)
        assert any(f["name"] == "Swords" for f in folders)

    def test_rename_folder(self, controller):
        fid = controller.create_bank_folder("OldName", None)
        controller.rename_bank_folder(fid, "NewName")
        folder = controller.get_bank_folder_by_id(fid)
        assert folder["name"] == "NewName"

    def test_delete_folder(self, controller):
        fid = controller.create_bank_folder("ToDelete", None)
        controller.delete_bank_folder(fid)
        assert controller.get_bank_folder_by_id(fid) is None

    def test_create_nested_folder(self, controller):
        parent_id = controller.create_bank_folder("Parent", None)
        child_id  = controller.create_bank_folder("Child", parent_id)
        children  = controller.get_bank_subfolders(parent_id)
        assert any(f["id"] == child_id for f in children)

    def test_get_folder_path(self, controller):
        root_id = controller.create_bank_folder("Root", None)
        child_id = controller.create_bank_folder("Child", root_id)
        path = controller.get_bank_folder_path(child_id)
        assert len(path) == 2
        assert path[0]["id"] == root_id
        assert path[1]["id"] == child_id

    def test_is_ancestor(self, controller):
        ancestor = controller.create_bank_folder("Ancestor", None)
        middle   = controller.create_bank_folder("Middle", ancestor)
        leaf     = controller.create_bank_folder("Leaf", middle)
        assert controller.is_bank_folder_ancestor(ancestor, leaf) is True
        assert controller.is_bank_folder_ancestor(leaf, ancestor) is False

    def test_move_item_to_folder(self, controller):
        fid = controller.create_bank_folder("Weapons", None)
        add_item_to_inv(controller, "bank", "Sword", seq_id=99)
        controller.move_bank_item_to_folder(99, fid)
        items = controller.get_bank_items_in_folder(fid)
        assert len(items) == 1

    def test_delete_folder_moves_items_to_root(self, controller):
        fid = controller.create_bank_folder("DeleteMe", None)
        add_item_to_inv(controller, "bank", "OrphanItem", seq_id=55)
        controller.move_bank_item_to_folder(55, fid)
        controller.delete_bank_folder(fid)
        # Item should now be at root (folder_id = None)
        items_at_root = controller.get_bank_items_in_folder(None)
        names = [item.name for _, item in items_at_root]
        assert "OrphanItem" in names

    def test_move_folder_to_new_parent(self, controller):
        parent_a = controller.create_bank_folder("ParentA", None)
        parent_b = controller.create_bank_folder("ParentB", None)
        child    = controller.create_bank_folder("Child", parent_a)
        controller.move_bank_folder_to_folder(child, parent_b)
        f = controller.get_bank_folder_by_id(child)
        assert f["parent_id"] == parent_b


# ─── POOL_NAME_BLACKLIST ──────────────────────────────────────────────────────

class TestPoolBlacklist:
    def test_soul_jar_full_not_in_pool(self, controller):
        raw = make_raw(name="SoulJar_Full", seq_id=1)
        name = raw.get("name")
        from app_controller import POOL_NAME_BLACKLIST
        assert name in POOL_NAME_BLACKLIST
        assert name not in controller.items_pool

    def test_normal_item_not_blacklisted(self, controller):
        from app_controller import POOL_NAME_BLACKLIST
        assert "TestItem" not in POOL_NAME_BLACKLIST


# ─── check_save_changed ───────────────────────────────────────────────────────

class TestCheckSaveChanged:
    def test_no_change_after_load(self, controller):
        changed, mtime, _ = controller.check_save_changed()
        assert changed is False

    def test_detects_file_write(self, controller):
        import time, os
        # Touch the file to change its mtime
        time.sleep(0.01)
        os.utime(controller.sav_path, None)
        changed, _, _ = controller.check_save_changed()
        assert changed is True


# ─── get_save_date_str ────────────────────────────────────────────────────────

class TestGetSaveDateStr:
    def test_returns_string(self, controller):
        result = controller.get_save_date_str()
        assert isinstance(result, str)

    def test_contains_emoji(self, controller):
        result = controller.get_save_date_str()
        assert "💾" in result

