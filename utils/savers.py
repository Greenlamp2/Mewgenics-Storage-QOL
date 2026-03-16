import json
import os
import sqlite3

from utils.save_manager import TOKENS_BANK_PATH
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
