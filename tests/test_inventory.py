"""
tests/test_inventory.py
=======================
Tests for Inventory parsing and the build_inventory_blob ↔ Inventory round-trip.
The item catalog is mocked so no data files are required.
"""
import struct

from tests.helpers import make_raw, build_blob
from utils.savers import build_inventory_blob


# ─── build_inventory_blob ─────────────────────────────────────────────────────

class TestBuildInventoryBlob:
    def test_empty_list_returns_none(self):
        assert build_inventory_blob([]) is None

    def test_none_returns_none(self):
        assert build_inventory_blob(None) is None  # type: ignore

    def test_single_item_has_correct_count(self, mock_item_catalog):
        raw = make_raw(name="Sword")
        blob = build_inventory_blob([raw])
        count = struct.unpack_from("<I", blob, 0)[0]
        assert count == 1

    def test_single_item_has_version_5(self, mock_item_catalog):
        raw = make_raw()
        blob = build_inventory_blob([raw])
        version = struct.unpack_from("<I", blob, 4)[0]
        assert version == 5

    def test_multiple_items_count(self, mock_item_catalog):
        raws = [make_raw(name=f"Item{i}", seq_id=i) for i in range(5)]
        blob = build_inventory_blob(raws)
        count = struct.unpack_from("<I", blob, 0)[0]
        assert count == 5

    def test_returns_bytes(self, mock_item_catalog):
        blob = build_inventory_blob([make_raw()])
        assert isinstance(blob, bytes)


# ─── Inventory parsing ────────────────────────────────────────────────────────

class TestInventoryParse:
    def test_empty_blob_gives_zero_count(self, mock_item_catalog):
        from parse.inventory import Inventory
        blob = struct.pack("<I", 0)
        inv = Inventory(blob)
        assert inv.count == 0
        assert inv.raws == []
        assert inv.items == []

    def test_none_blob_gives_zero_count(self, mock_item_catalog):
        from parse.inventory import Inventory
        inv = Inventory(None)
        assert inv.count == 0

    def test_single_item_parsed(self, mock_item_catalog):
        from parse.inventory import Inventory
        raw = make_raw(name="TestSword", seq_id=1)
        blob = build_inventory_blob([raw])
        inv = Inventory(blob)
        assert inv.count == 1
        assert len(inv.raws) == 1
        assert inv.raws[0]["name"] == "TestSword"

    def test_three_items_parsed(self, mock_item_catalog):
        from parse.inventory import Inventory
        raws = [make_raw(name=f"Item{i}", seq_id=i + 1) for i in range(3)]
        blob = build_inventory_blob(raws)
        inv = Inventory(blob)
        assert inv.count == 3
        names = [r["name"] for r in inv.raws]
        assert names == ["Item0", "Item1", "Item2"]

    def test_item_fields_preserved(self, mock_item_catalog):
        from parse.inventory import Inventory
        raw = make_raw(name="Spear", subname="Sharp", charges=5,
                       field1=10, field2=20, seq_id=7, tail_byte=0, sep_flag=1)
        blob = build_inventory_blob([raw])
        inv = Inventory(blob)
        r = inv.raws[0]
        assert r["name"]    == "Spear"
        assert r["subname"] == "Sharp"
        assert r["charges"] == 5
        assert r["field1"]  == 10
        assert r["field2"]  == 20
        assert r["seqId"]   == 7
        assert r["sep_flag"] == 1

    def test_trash_flag_passed_to_items(self, mock_item_catalog):
        from parse.inventory import Inventory
        raw = make_raw(sep_flag=5)
        blob = build_inventory_blob([raw])
        inv_trash   = Inventory(blob, trash=True)
        inv_storage = Inventory(blob, trash=False)
        assert inv_trash.items[0].broken   is True
        assert inv_storage.items[0].broken is False

    def test_items_count_matches_raws(self, mock_item_catalog):
        from parse.inventory import Inventory
        raws = [make_raw(seq_id=i) for i in range(4)]
        blob = build_inventory_blob(raws)
        inv = Inventory(blob)
        assert len(inv.items) == len(inv.raws) == 4

    def test_negative_charges_preserved(self, mock_item_catalog):
        from parse.inventory import Inventory
        raw = make_raw(charges=-1)
        blob = build_inventory_blob([raw])
        inv = Inventory(blob)
        assert inv.raws[0]["charges"] == -1


# ─── Round-trip: build → parse → build → compare ─────────────────────────────

class TestInventoryRoundTrip:
    def _round_trip(self, raws: list) -> tuple[bytes, bytes]:
        """Build blob, parse inventory, re-build blob."""
        from parse.inventory import Inventory
        blob1 = build_inventory_blob(raws)
        inv   = Inventory(blob1)
        blob2 = build_inventory_blob(inv.raws)
        return blob1, blob2

    def test_single_item_byte_perfect(self, mock_item_catalog):
        raws = [make_raw(name="GlassShard", seq_id=1)]
        b1, b2 = self._round_trip(raws)
        assert b1 == b2

    def test_five_items_byte_perfect(self, mock_item_catalog):
        raws = [make_raw(name=f"Item{i}", seq_id=i + 1) for i in range(5)]
        b1, b2 = self._round_trip(raws)
        assert b1 == b2

    def test_item_with_subname_byte_perfect(self, mock_item_catalog):
        raws = [make_raw(name="Sword", subname="Sharp", seq_id=1)]
        b1, b2 = self._round_trip(raws)
        assert b1 == b2

    def test_mixed_rarities_byte_perfect(self, mock_item_catalog):
        raws = [
            make_raw(name="CommonItem",   sep_flag=1, seq_id=1),
            make_raw(name="BrokenItem",   sep_flag=5, seq_id=2),
            make_raw(name="UsedItem",     sep_flag=3, seq_id=3),
        ]
        b1, b2 = self._round_trip(raws)
        assert b1 == b2

    def test_raws_preserved_after_parse(self, mock_item_catalog):
        from parse.inventory import Inventory
        raws = [make_raw(name=f"X{i}", seq_id=i) for i in range(3)]
        blob = build_inventory_blob(raws)
        inv  = Inventory(blob)
        for orig, parsed in zip(raws, inv.raws):
            assert parsed["name"]   == orig["name"]
            assert parsed["seqId"]  == orig["seqId"]

