"""
tests/helpers.py
================
Shared pure-function helpers and constants used across the test suite.
No pytest fixtures here — those live in conftest.py.
"""
import struct
import sqlite3


# ─── Mock item details ────────────────────────────────────────────────────────

MOCK_ITEM_DETAILS = {
    "rarity": "common",
    "ability": None,
    "passives": {},
    "desc": "TestItem",
    "name_resolved": "TestItem",
}
MOCK_RARE_DETAILS      = {**MOCK_ITEM_DETAILS, "rarity": "rare"}
MOCK_UNCOMMON_DETAILS  = {**MOCK_ITEM_DETAILS, "rarity": "uncommon"}
MOCK_VERY_RARE_DETAILS = {**MOCK_ITEM_DETAILS, "rarity": "very_rare"}


# ─── Raw item factory ─────────────────────────────────────────────────────────

def make_raw(name: str = "TestItem", subname: str = "", charges: int = -1,
             field1: int = 0, field2: int = 0, seq_id: int = 1,
             tail_byte: int = 0, sep_flag: int = 1) -> dict:
    """Build a minimal item raw dict suitable for Inventory / AppController tests."""
    return {
        "name": name, "subname": subname, "charges": charges,
        "field1": field1, "field2": field2, "seqId": seq_id,
        "tailByte": tail_byte, "sep_flag": sep_flag,
    }


# ─── Blob helpers ─────────────────────────────────────────────────────────────

def build_blob(raws: list) -> bytes:
    """Build a valid inventory blob from a list of raw item dicts.

    Returns a 4-byte zero blob for empty lists (count = 0).
    """
    from utils.savers import build_inventory_blob
    if not raws:
        return struct.pack("<I", 0)
    result = build_inventory_blob(raws)
    return result if result is not None else struct.pack("<I", 0)


# ─── Minimal SQLite save DB ───────────────────────────────────────────────────

def setup_save_db(path: str,
                  storage_raws: list | None = None,
                  trash_raws:   list | None = None,
                  gold:         int  = 100,
                  tokens:       dict | None = None,
                  current_day:  int  = 42) -> None:
    """Create a minimal but structurally valid Mewgenics SQLite save file."""
    if tokens is None:
        tokens = {"common": 5, "uncommon": 3, "rare": 1, "very_rare": 0}

    storage_blob = build_blob(storage_raws or [])
    trash_blob   = build_blob(trash_raws or [])

    conn = sqlite3.connect(path)

    # files table (inventory + state blobs)
    conn.execute("CREATE TABLE files (key TEXT PRIMARY KEY, data BLOB)")
    conn.execute("INSERT INTO files VALUES ('inventory_storage', ?)", (storage_blob,))
    conn.execute("INSERT INTO files VALUES ('inventory_trash',   ?)", (trash_blob,))
    # house_state: 4-byte header + u32 count=0
    conn.execute("INSERT INTO files VALUES ('house_state', ?)",
                 (struct.pack("<II", 0, 0),))
    # adventure_state: 4-byte unknown + u32 count=0
    conn.execute("INSERT INTO files VALUES ('adventure_state', ?)",
                 (struct.pack("<II", 0, 0),))
    # pedigree: 8-byte header, no entries
    conn.execute("INSERT INTO files VALUES ('pedigree', ?)",
                 (struct.pack("<Q", 0),))

    # properties table
    conn.execute("CREATE TABLE properties (key TEXT PRIMARY KEY, data)")
    props = [
        ("house_gold",            str(gold)),
        ("current_day",           str(current_day)),
        ("house_food",            "50"),
        ("save_file_percent",     "0.5"),
        ("BonusBirdsKilled",      "7"),
        ("current_house_weather", "Sunny"),
    ]
    conn.executemany("INSERT INTO properties VALUES (?, ?)", props)

    # custom table (tokens + other persisted state)
    conn.execute("CREATE TABLE custom (key TEXT PRIMARY KEY, data TEXT)")
    for rarity, count in tokens.items():
        conn.execute("INSERT INTO custom VALUES (?, ?)", (rarity, str(count)))

    # other tables expected by AppController
    conn.execute("CREATE TABLE cats   (key INTEGER PRIMARY KEY, data BLOB)")
    conn.execute("CREATE TABLE bank   (key TEXT PRIMARY KEY, data BLOB)")
    conn.execute(
        "CREATE TABLE cat_bank "
        "(key INTEGER PRIMARY KEY, entry_bytes BLOB, room_name TEXT)"
    )

    conn.commit()
    conn.close()


# ─── AppController item helper ────────────────────────────────────────────────

def add_item_to_inv(ctrl, inv_key: str, name: str = "TestItem",
                    sep_flag: int = 1, seq_id: int | None = None) -> dict:
    """Append an item directly to an in-memory inventory without writing to disk.

    Useful for setting up AppController state before testing a command method.
    """
    from parse.item import Item
    inv = ctrl.inventories[inv_key]
    sid = seq_id if seq_id is not None else inv.count + 1
    raw = make_raw(name=name, seq_id=sid, sep_flag=sep_flag)
    inv.raws.append(raw)
    inv.items.append(Item(raw, trash=(inv_key == "trash")))
    inv.count += 1
    return raw

