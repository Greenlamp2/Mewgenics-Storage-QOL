import sqlite3

from parse.inventory import Inventory


def load_inventories(path):
    conn = sqlite3.connect(path)
    backpackBlob = conn.execute("SELECT key, data FROM files WHERE key=\'inventory_backpack\'").fetchone()[1]
    storageBlob = conn.execute("SELECT key, data FROM files WHERE key=\'inventory_storage\'").fetchone()[1]
    trashBlob = conn.execute("SELECT key, data FROM files WHERE key=\'inventory_trash\'").fetchone()[1]
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
