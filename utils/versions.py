import itertools
import sqlite3

from parse.inventory import Inventory
from utils.savers import build_inventory_blob


def compare_blob(original, duplicate):
    diff = None
    for i, (a, b) in enumerate(zip(duplicate, original)):
        if a != b:
            diff = i
            break

    if diff is not None:
        start = max(0, diff - 16)
        end = diff + 16

        print("orig:", original[start:end].hex(" "))
        print("test:", duplicate[start:end].hex(" "))

    for i, (a, b) in enumerate(itertools.zip_longest(duplicate, original)):
        if a != b:
            print("diff at", i)
            return False
            break

    return True

def is_app_up_most_to_date(path):
    conn = sqlite3.connect(path)
    storageBlob = conn.execute("SELECT key, data FROM files WHERE key=\'inventory_storage\'").fetchone()[1]
    storage = Inventory(storageBlob)
    blob = build_inventory_blob(storage.raws)
    return compare_blob(storageBlob, blob)