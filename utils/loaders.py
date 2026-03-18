import json
import os
import sqlite3

from parse.inventory import Inventory
from utils.save_manager import TOKENS_BANK_PATH, ITEMS_POOL_PATH

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

def load_tokens(save_mtime: float | None = None):
    """Return tokens for the given save file mtime.

    Normal flow  : save_mtime >= current_save_mtime  → returns "current" (always up-to-date)
    Time-travel  : save_mtime <  current_save_mtime  → finds latest history snapshot ≤ save_mtime
    No file/empty: returns all zeros
    Handles migration from the old flat-dict format.
    """
    empty = {rarity: 0 for rarity in RARITIES}

    if not os.path.exists(TOKENS_BANK_PATH):
        return empty

    with open(TOKENS_BANK_PATH, encoding="utf-8") as f:
        data = json.load(f)

    # ── Migration: old flat format {"common": N, …} ───────────────────
    if "history" not in data and "current" not in data:
        snapshot_tokens = {r: data.get(r, 0) for r in RARITIES}
        data = {
            "current": snapshot_tokens,
            "current_save_mtime": 0.0,
            "history": [{"save_mtime": 0.0, "tokens": snapshot_tokens}],
        }
        os.makedirs(os.path.dirname(TOKENS_BANK_PATH), exist_ok=True)
        with open(TOKENS_BANK_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

    # ── Migration: history-only format (previous version of this app) ─
    elif "history" in data and "current" not in data:
        hist = sorted(data["history"], key=lambda s: s["save_mtime"])
        latest = hist[-1] if hist else {}
        data["current"]            = latest.get("tokens", dict(empty))
        data["current_save_mtime"] = latest.get("save_mtime", 0.0)
        os.makedirs(os.path.dirname(TOKENS_BANK_PATH), exist_ok=True)
        with open(TOKENS_BANK_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

    current        = data.get("current", empty)
    current_mtime  = data.get("current_save_mtime", 0.0)
    history        = sorted(data.get("history", []), key=lambda s: s["save_mtime"])

    # No mtime supplied → always return the most recent state
    if save_mtime is None:
        return {rarity: current.get(rarity, 0) for rarity in RARITIES}

    # Normal case: the loaded save is at least as recent as when tokens were last saved
    if save_mtime >= current_mtime:
        return {rarity: current.get(rarity, 0) for rarity in RARITIES}

    # Time-travel: the loaded save is OLDER than the last token save → use history
    candidates = [s for s in history if s["save_mtime"] <= save_mtime]
    if candidates:
        tokens = candidates[-1]["tokens"]
    elif history:
        tokens = history[0]["tokens"]   # oldest available
    else:
        return empty

    return {rarity: tokens.get(rarity, 0) for rarity in RARITIES}

def load_items_pool():
    if not os.path.exists(ITEMS_POOL_PATH):
        return {}
    with open(ITEMS_POOL_PATH, encoding="utf-8") as f:
        return json.load(f)
