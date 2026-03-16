import json
import os
import sqlite3

from parse.inventory import Inventory
from utils.save_manager import TOKENS_BANK_PATH, ITEMS_POOL_PATH

RARITIES = ("common", "uncommon", "rare", "very_rare")


def _fetch_blob(conn, key):
    row = conn.execute("SELECT data FROM files WHERE key=?", (key,)).fetchone()
    return row[0] if row else None

def load_inventories(path):
    conn = sqlite3.connect(path)
    backpackBlob = _fetch_blob(conn, 'inventory_backpack')
    storageBlob  = _fetch_blob(conn, 'inventory_storage')
    trashBlob    = _fetch_blob(conn, 'inventory_trash')
    storage = Inventory(storageBlob)
    backpack = Inventory(backpackBlob)
    trash = Inventory(trashBlob)
    conn.close()

    return {
        'backpack': backpack,
        'storage': storage,
        'trash': trash,
    }

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

def load_tokens():
    if not os.path.exists(TOKENS_BANK_PATH):
        return {rarity: 0 for rarity in RARITIES}
    with open(TOKENS_BANK_PATH, encoding="utf-8") as f:
        data = json.load(f)
    return {rarity: data.get(rarity, 0) for rarity in RARITIES}

def load_items_pool():
    if not os.path.exists(ITEMS_POOL_PATH):
        return {}
    with open(ITEMS_POOL_PATH, encoding="utf-8") as f:
        return json.load(f)
