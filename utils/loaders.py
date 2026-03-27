import json
import os
import sqlite3
import struct

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


def _fetch_blob(conn, key, table="files"):
    query = f"SELECT data FROM {table} WHERE key=?"
    row = conn.execute(query, (key,)).fetchone()
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

def load_house_infos(path):
    _, house_info, _ = load_house_state_raw(path)
    return house_info


def load_house_state_raw(path: str) -> tuple:
    """Parse the house_state blob with full round-trip capability.

    Returns:
        header_prefix (bytes): first 4 bytes of the blob (unknown header; preserved verbatim)
        house_info    (dict):  {cat_key (int): room_name (str)}  — passed to Cat.__init__
        entries       (dict):  {cat_key (int): raw_entry_bytes (bytes)}  — used for banking
    """
    empty = (b'\x00\x00\x00\x00', {}, {})
    if not os.path.exists(path):
        return empty
    try:
        conn = sqlite3.connect(path)
        data = _fetch_blob(conn, 'house_state')
        conn.close()
    except Exception:
        return empty

    if not data or len(data) < 8:
        return data[:4] if data and len(data) >= 4 else b'\x00\x00\x00\x00', {}, {}

    header_prefix = data[0:4]
    count = struct.unpack_from('<I', data, 4)[0]
    pos   = 8
    house_info: dict = {}
    entries:    dict = {}

    for _ in range(count):
        entry_start = pos
        if pos + 8 > len(data):
            break
        cat_key  = struct.unpack_from('<I', data, pos)[0]
        pos += 8
        if pos + 8 > len(data):
            break
        room_len = struct.unpack_from('<I', data, pos)[0]
        pos += 8
        room_name = ""
        if room_len > 0:
            if pos + room_len > len(data):
                break
            room_name = data[pos:pos + room_len].decode('ascii', errors='ignore')
            pos += room_len
        if pos + 24 > len(data):
            entry_end = len(data)
        else:
            pos += 24
            entry_end = pos
        house_info[cat_key] = room_name
        entries[cat_key]    = bytes(data[entry_start:entry_end])

    return header_prefix, house_info, entries


def load_cat_bank(path: str) -> dict:
    """Load the cat bank from the ``cat_bank`` SQLite table.

    Returns {db_key (int): {'entry_bytes': bytes, 'room_name': str}}.
    Creates the table automatically if it does not exist.
    """
    if not os.path.exists(path):
        return {}
    try:
        conn = sqlite3.connect(path)
        conn.execute(
            "CREATE TABLE IF NOT EXISTS cat_bank "
            "(key INTEGER PRIMARY KEY, entry_bytes BLOB, room_name TEXT)"
        )
        conn.commit()
        rows = conn.execute(
            "SELECT key, entry_bytes, room_name FROM cat_bank"
        ).fetchall()
        conn.close()
        return {
            int(k): {
                'entry_bytes': bytes(eb) if eb else b'',
                'room_name':   rn or '',
            }
            for k, eb, rn in rows
        }
    except Exception:
        return {}

def load_adventure_keys(path):
    conn = sqlite3.connect(path)
    keys = set()
    try:
        data = _fetch_blob(conn, 'adventure_state')
        if not data:
            return keys
        count = struct.unpack_from('<I', data, 4)[0]
        pos   = 8
        for _ in range(count):
            if pos + 8 > len(data):
                break
            val = struct.unpack_from('<Q', data, pos)[0]
            pos += 8
            cat_key = (val >> 32) & 0xFFFF_FFFF
            if cat_key:
                keys.add(cat_key)
    except Exception:
        pass
    return keys

def load_cats(path):
    conn = sqlite3.connect(path)
    rows  = conn.execute("SELECT key, data FROM cats").fetchall()
    return rows

def load_pedigree(path):
    """
    Parse the pedigree blob from the files table.
    Each 32-byte entry: u64 cat_key, u64 parent_a_key, u64 parent_b_key, u64 extra.
    0xFFFFFFFFFFFFFFFF means null/unknown for parent fields.

    Returns ped_map: db_key -> (parent_a_db_key | None, parent_b_db_key | None).

    NOTE: children are NOT derived from this map because the pedigree blob
    appears to store more than just direct parent-child pairs (possibly full
    lineage chains), which causes circular references when used for children.
    Children are instead computed bottom-up from resolved parent fields.
    """
    conn = sqlite3.connect(path)
    try:
        data = _fetch_blob(conn, 'pedigree')
        if not data:
            return {}
    except Exception:
        return {}

    NULL = 0xFFFF_FFFF_FFFF_FFFF
    MAX_KEY = 1_000_000   # anything larger is a legacy UID or garbage
    ped_map: dict = {}

    # Entries start at offset 8 (after a single u64 header), stride 32
    for pos in range(8, len(data) - 31, 32):
        cat_k, pa_k, pb_k, extra = struct.unpack_from('<QQQQ', data, pos)
        if cat_k == 0 or cat_k == NULL or cat_k > MAX_KEY:
            continue
        pa = int(pa_k) if pa_k != NULL and 0 < pa_k <= MAX_KEY else None
        pb = int(pb_k) if pb_k != NULL and 0 < pb_k <= MAX_KEY else None
        cat_key = int(cat_k)

        existing = ped_map.get(cat_key)
        if existing is None:
            # No entry yet — take whatever we have
            ped_map[cat_key] = (pa, pb)
        elif existing[0] is None or existing[1] is None:
            # Existing entry is incomplete — upgrade if this one is better
            if pa is not None and pb is not None:
                ped_map[cat_key] = (pa, pb)

    return ped_map

def load_current_day(path):
    conn = sqlite3.connect(path)
    return _fetch_blob(conn, 'current_day', 'properties')


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

def load_newborn_kills(path: str) -> int:
    """Load the cumulative newborn-kill counter from the ``custom`` table."""
    if not os.path.exists(path):
        return 0
    try:
        conn = sqlite3.connect(path)
        conn.execute("CREATE TABLE IF NOT EXISTS custom (key TEXT PRIMARY KEY, data TEXT)")
        conn.commit()
        row = conn.execute(
            "SELECT data FROM custom WHERE key='newborn_kills'"
        ).fetchone()
        conn.close()
        return int(row[0]) if row and row[0] else 0
    except Exception:
        return 0


def load_items_pool():
    if not os.path.exists(ITEMS_POOL_PATH):
        return {}
    with open(ITEMS_POOL_PATH, encoding="utf-8") as f:
        return json.load(f)


BANK_FOLDERS_KEY = "bank_folders_v1"

CAT_TAGS_KEY = "cat_tags_v1"

def load_cat_tags(path: str) -> dict:
    """Load cat tags from the ``custom`` table.

    Returns {db_key (int): [list of tag strings]}.
    """
    if not os.path.exists(path):
        return {}
    try:
        conn = sqlite3.connect(path)
        conn.execute("CREATE TABLE IF NOT EXISTS custom (key TEXT PRIMARY KEY, data TEXT)")
        conn.commit()
        row = conn.execute(
            "SELECT data FROM custom WHERE key=?", (CAT_TAGS_KEY,)
        ).fetchone()
        conn.close()
        if row and row[0]:
            data = json.loads(row[0])
            return {int(k): v for k, v in data.items() if isinstance(v, list)}
    except Exception:
        pass
    return {}


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

