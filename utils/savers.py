import json
import os
import sqlite3
import struct

from utils.save_manager import ITEMS_POOL_PATH
from utils.writers import BinaryWriter


def build_inventory_blob(items):
    if not items:
        return
    writer = BinaryWriter()

    writer.u32(len(items))
    writer.u32(5)  # version

    for i, item in enumerate(items):

        writer.u8(1)  # flag
        writer.str(item.get('name'))
        writer.str(item.get('subname', ''))

        writer.i32(item.get('charges'))
        writer.u32(item.get('field1'))
        writer.u32(item.get('field2'))
        writer.u32(item.get('seqId'))

        writer.u8(item.get('tailByte'))

        if i < len(items) - 1:
            writer.u8(item.get('sep_flag'))
            writer.u32(5)
        else:
            writer.u8(item.get('sep_flag'))

    return writer.get()


def save_inventories(path, inventories):
    conn = sqlite3.connect(path)
    storage = inventories.get('storage')
    trash = inventories.get('trash')
    storageBlob = build_inventory_blob(storage.raws)
    conn.execute(
        "UPDATE files SET data=? WHERE key='inventory_storage'",
        (storageBlob,)
    )

    trashBlob = build_inventory_blob(trash.raws)
    conn.execute(
        "UPDATE files SET data=? WHERE key='inventory_trash'",
        (trashBlob,)
    )

    conn.commit()
    conn.close()


def save_gold(path, gold):
    conn = sqlite3.connect(path)
    conn.execute("UPDATE properties SET data=? WHERE key='house_gold'", (int(gold),))
    conn.commit()
    conn.close()


def save_bank_inventory(path: str, inventory):
    """Persist the bank inventory to the 'bank' table in the save file.

    Schema: bank (key TEXT PRIMARY KEY, data BLOB)
    An empty inventory is stored as a minimal blob (count = 0).
    """
    blob = build_inventory_blob(inventory.raws)
    if blob is None:
        # Empty inventory: write a 4-byte little-endian 0 (count = 0)
        import struct
        blob = struct.pack("<I", 0)
    conn = sqlite3.connect(path)
    conn.execute(
        "CREATE TABLE IF NOT EXISTS bank "
        "(key TEXT PRIMARY KEY, data BLOB);"
    )
    conn.execute(
        "INSERT OR REPLACE INTO bank (key, data) VALUES ('inventory_bank', ?);",
        (blob,),
    )
    conn.commit()
    conn.close()


def save_tokens(sav_path: str, tokens: dict):
    """Persist token counts to the 'custom' table in the save file.

    Schema: custom (key TEXT PRIMARY KEY, data TEXT)
    One row per rarity: key = rarity name, data = count as string.
    """
    conn = sqlite3.connect(sav_path)
    conn.execute(
        "CREATE TABLE IF NOT EXISTS custom "
        "(key TEXT PRIMARY KEY, data TEXT);"
    )
    for rarity, count in tokens.items():
        conn.execute(
            "INSERT OR REPLACE INTO custom (key, data) VALUES (?, ?);",
            (rarity, str(int(count))),
        )
    conn.commit()
    conn.close()


def add_item_to_pool(raw):
    """Add the item to the pool if its name does not already exist. Returns True if added."""
    from utils.loaders import load_items_pool
    name = raw.get("name")
    if not name:
        return False
    pool = load_items_pool()
    if name in pool:
        return False
    pool[name] = raw
    os.makedirs(os.path.dirname(ITEMS_POOL_PATH), exist_ok=True)
    with open(ITEMS_POOL_PATH, "w", encoding="utf-8") as f:
        json.dump(pool, f, indent=2)
    return True


def remove_from_pool(name):
    """Remove the item from the pool by name. Returns True if removed."""
    from utils.loaders import load_items_pool
    pool = load_items_pool()
    if name not in pool:
        return False
    del pool[name]
    os.makedirs(os.path.dirname(ITEMS_POOL_PATH), exist_ok=True)
    with open(ITEMS_POOL_PATH, "w", encoding="utf-8") as f:
        json.dump(pool, f, indent=2)
    return True


def save_items_pool(pool):
    os.makedirs(os.path.dirname(ITEMS_POOL_PATH), exist_ok=True)
    with open(ITEMS_POOL_PATH, "w", encoding="utf-8") as f:
        json.dump(pool, f, indent=2)


def save_cat(sav_path: str, cat) -> None:
    """Compress and persist a single cat blob to the ``cats`` table.

    Call this after ``cat.rename_in_blob()`` (or any other in-place mutation)
    to flush the changes back to the save file.
    """
    blob = cat.to_blob()
    conn = sqlite3.connect(sav_path)
    conn.execute("UPDATE cats SET data=? WHERE key=?", (blob, cat.db_key))
    conn.commit()
    conn.close()


def save_new_cat(sav_path: str, blob: bytes) -> int:
    """Insert a brand-new cat blob into the ``cats`` table and return the new db_key.

    The new key is ``max(existing_keys) + 1``.  The blob should be an
    LZ4-compressed cat blob as produced by ``Cat.to_blob()``.
    """
    conn = sqlite3.connect(sav_path)
    row = conn.execute("SELECT MAX(key) FROM cats").fetchone()
    new_key = (row[0] if row and row[0] is not None else 0) + 1
    conn.execute("INSERT INTO cats (key, data) VALUES (?, ?)", (new_key, blob))
    conn.commit()
    conn.close()
    return new_key


_BANK_FOLDERS_KEY = "bank_folders_v1"

def save_bank_folders(sav_path: str, data: dict):
    """Persist bank folder structure to the SQLite custom table."""
    conn = sqlite3.connect(sav_path)
    conn.execute("CREATE TABLE IF NOT EXISTS custom (key TEXT PRIMARY KEY, data TEXT)")
    conn.execute(
        "INSERT OR REPLACE INTO custom (key, data) VALUES (?, ?)",
        (_BANK_FOLDERS_KEY, json.dumps(data, ensure_ascii=False)),
    )
    conn.commit()
    conn.close()


def save_house_state(path: str, header_prefix: bytes, entries: dict) -> None:
    """Write the house_state blob back to the save file.

    Parameters
    ----------
    header_prefix : bytes
        The first 4 bytes of the original blob (unknown header; preserved verbatim).
    entries : dict
        {cat_key (int): raw_entry_bytes (bytes)} — only cats that should remain
        in the house.  Cats omitted here will no longer be tracked by the game
        as being in the house.
    """
    count = len(entries)
    blob  = (
        header_prefix[:4]
        + struct.pack('<I', count)
        + b''.join(entries.values())
    )
    conn = sqlite3.connect(path)
    conn.execute("UPDATE files SET data=? WHERE key='house_state'", (blob,))
    conn.commit()
    conn.close()


def save_cat_bank(path: str, cat_bank: dict) -> None:
    """Persist the cat bank to the ``cat_bank`` SQLite table.

    Parameters
    ----------
    cat_bank : dict
        {db_key (int): {'entry_bytes': bytes, 'room_name': str}}
    """
    conn = sqlite3.connect(path)
    conn.execute(
        "CREATE TABLE IF NOT EXISTS cat_bank "
        "(key INTEGER PRIMARY KEY, entry_bytes BLOB, room_name TEXT)"
    )
    conn.execute("DELETE FROM cat_bank")
    for db_key, data in cat_bank.items():
        conn.execute(
            "INSERT INTO cat_bank (key, entry_bytes, room_name) VALUES (?, ?, ?)",
            (int(db_key), data['entry_bytes'], data.get('room_name', '')),
        )
    conn.commit()
    conn.close()


