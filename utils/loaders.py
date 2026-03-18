import json
import os
import sqlite3

from parse.inventory import Inventory
from utils.save_manager import TOKENS_BANK_PATH, ITEMS_POOL_PATH  # TOKENS_BANK_PATH kept for migration only

RARITIES = ("common", "uncommon", "rare", "very_rare")

SAVE_INFO_KEYS = [
    "BonusBirdsKilled",
    "house_food",
    "house_gold",
    "save_file_percent",
    "current_day",
    "current_house_weather",
]


def load_save_properties(path: str, keys: list[str]) -> dict[str, str]:
    """Fetch multiple properties from the 'properties' table. Returns {key: raw_value_str}."""
    empty = {k: "" for k in keys}
    if not os.path.exists(path):
        return empty
    conn = sqlite3.connect(path)
    result: dict[str, str] = {}
    for key in keys:
        row = conn.execute("SELECT data FROM properties WHERE key=?", (key,)).fetchone()
        result[key] = row[0] if row else ""
    conn.close()
    return result


def load_cats_count(path: str) -> int:
    """Return the number of rows in the 'cats' table (= total cats seen)."""
    if not os.path.exists(path):
        return 0
    try:
        conn = sqlite3.connect(path)
        row = conn.execute("SELECT COUNT(*) FROM cats").fetchone()
        conn.close()
        return int(row[0]) if row else 0
    except Exception:
        return 0


def _fetch_blob(conn, key):
    row = conn.execute("SELECT data FROM files WHERE key=?", (key,)).fetchone()
    return row[0] if row else None

def load_inventories(path):
    conn = sqlite3.connect(path)
    storageBlob  = _fetch_blob(conn, 'inventory_storage')
    trashBlob    = _fetch_blob(conn, 'inventory_trash')
    storage = Inventory(storageBlob)
    trash = Inventory(trashBlob, True)
    conn.close()

    return {
        'storage': storage,
        'trash': trash,
    }


def load_bank_inventory(path: str) -> Inventory:
    """Load the bank inventory from the 'bank' table in the save file.

    The table is created automatically if it does not exist yet.
    Schema: bank (key TEXT PRIMARY KEY, data BLOB)
    The inventory blob is stored under key 'inventory_bank'.
    """
    if not os.path.exists(path):
        return Inventory(None)
    try:
        conn = sqlite3.connect(path)
        conn.execute(
            "CREATE TABLE IF NOT EXISTS bank "
            "(key TEXT PRIMARY KEY, data BLOB);"
        )
        conn.commit()
        row = conn.execute(
            "SELECT data FROM bank WHERE key='inventory_bank';"
        ).fetchone()
        conn.close()
        return Inventory(row[0] if row else None)
    except Exception:
        return Inventory(None)

def load_gold(path):
    conn = sqlite3.connect(path)
    row = conn.execute("SELECT key, data FROM properties WHERE key='house_gold'").fetchone()
    conn.close()
    if row is None:
        return 0
    try:
        return int(row[1])
    except (TypeError, ValueError):
        return 0

def load_tokens(sav_path: str) -> dict[str, int]:
    """Read token counts from the 'custom' table in the save file.

    Schema: custom (key TEXT PRIMARY KEY, data TEXT)
    One row per rarity: key = rarity name, data = count as string.

    On first run, if the table has no token data yet and a legacy
    tokens_bank.json file exists, its values are returned so the
    caller can persist them to SQLite via save_tokens().
    """
    empty = {rarity: 0 for rarity in RARITIES}
    if not os.path.exists(sav_path):
        return dict(empty)

    try:
        conn = sqlite3.connect(sav_path)
        conn.execute(
            "CREATE TABLE IF NOT EXISTS custom "
            "(key TEXT PRIMARY KEY, data TEXT);"
        )
        conn.commit()

        result: dict[str, int] = {}
        any_found = False
        for rarity in RARITIES:
            row = conn.execute(
                "SELECT data FROM custom WHERE key=?", (rarity,)
            ).fetchone()
            if row is not None:
                any_found = True
                try:
                    result[rarity] = int(row[0])
                except (ValueError, TypeError):
                    result[rarity] = 0
            else:
                result[rarity] = 0
        conn.close()
    except Exception:
        return dict(empty)

    # ── Migration: legacy tokens_bank.json → return its values so the
    #    controller will persist them to SQLite on the next save_tokens() call.
    if not any_found and os.path.exists(TOKENS_BANK_PATH):
        try:
            with open(TOKENS_BANK_PATH, encoding="utf-8") as f:
                data = json.load(f)
            # Support both flat {"common": N} and new {"current": {...}} formats
            source = data.get("current", data)
            return {rarity: int(source.get(rarity, 0)) for rarity in RARITIES}
        except Exception:
            pass

    return result

def load_items_pool():
    if not os.path.exists(ITEMS_POOL_PATH):
        return {}
    with open(ITEMS_POOL_PATH, encoding="utf-8") as f:
        return json.load(f)


BANK_FOLDERS_KEY = "bank_folders_v1"

def load_bank_folders(sav_path: str) -> dict:
    """Load the bank folder structure from the SQLite custom table.

    Returns {"folders": [...], "item_folders": {str(seq_id): folder_id_or_None}}.
    """
    empty = {"folders": [], "item_folders": {}}
    if not os.path.exists(sav_path):
        return empty
    try:
        conn = sqlite3.connect(sav_path)
        conn.execute("CREATE TABLE IF NOT EXISTS custom (key TEXT PRIMARY KEY, data TEXT)")
        conn.commit()
        row = conn.execute(
            "SELECT data FROM custom WHERE key=?", (BANK_FOLDERS_KEY,)
        ).fetchone()
        conn.close()
        if row:
            import json as _json
            return _json.loads(row[0])
    except Exception:
        pass
    return empty

