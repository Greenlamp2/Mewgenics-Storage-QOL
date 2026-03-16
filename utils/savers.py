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
        writer.str(item.get('subName', ''))

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
    backpack = inventories.get('backpack')
    trash = inventories.get('trash')
    storageBlob = build_inventory_blob(storage.raws)
    conn.execute(
        "UPDATE files SET data=? WHERE key='inventory_storage'",
        (storageBlob,)
    )

    backpackBlob = build_inventory_blob(backpack.raws)
    conn.execute(
        "UPDATE files SET data=? WHERE key='inventory_backpack'",
        (backpackBlob,)
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


def save_tokens(tokens):
    os.makedirs(os.path.dirname(TOKENS_BANK_PATH), exist_ok=True)
    with open(TOKENS_BANK_PATH, "w", encoding="utf-8") as f:
        json.dump(tokens, f, indent=2)


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
