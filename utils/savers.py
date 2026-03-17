import json
import os
import sqlite3

from utils.save_manager import TOKENS_BANK_PATH, ITEMS_POOL_PATH
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


def save_tokens(tokens: dict, save_mtime: float):
    """Save tokens. Always updates 'current' state; also upserts a history snapshot."""
    os.makedirs(os.path.dirname(TOKENS_BANK_PATH), exist_ok=True)

    # Load existing data
    if os.path.exists(TOKENS_BANK_PATH):
        with open(TOKENS_BANK_PATH, encoding="utf-8") as f:
            data = json.load(f)
        # Migrate old flat format (no "current" / "history")
        if "history" not in data and "current" not in data:
            from utils.loaders import RARITIES
            old_tokens = {r: data.get(r, 0) for r in RARITIES}
            data = {
                "current": old_tokens,
                "current_save_mtime": 0.0,
                "history": [{"save_mtime": 0.0, "tokens": old_tokens}],
            }
        # Migrate old history-only format (no "current")
        elif "history" in data and "current" not in data:
            history = sorted(data["history"], key=lambda s: s["save_mtime"])
            latest  = history[-1]["tokens"] if history else {}
            data["current"]            = latest
            data["current_save_mtime"] = history[-1]["save_mtime"] if history else 0.0
    else:
        data = {"current": {}, "current_save_mtime": 0.0, "history": []}

    # Always update "current"
    data["current"]            = dict(tokens)
    data["current_save_mtime"] = save_mtime

    # Upsert history snapshot
    history = data.get("history", [])
    for snapshot in history:
        if snapshot["save_mtime"] == save_mtime:
            snapshot["tokens"] = dict(tokens)
            break
    else:
        history.append({"save_mtime": save_mtime, "tokens": dict(tokens)})

    data["history"] = sorted(history, key=lambda s: s["save_mtime"])

    with open(TOKENS_BANK_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def add_item_to_pool(raw):
    """Ajoute l'item au pool si son nom n'existe pas déjà. Retourne True si ajouté."""
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
    """Retire l'item du pool par son nom. Retourne True si supprimé."""
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
