"""
Gift manager — send/receive items via a remote PostgreSQL trade table.

Connection is configured via a .env file at the project root:
  DATABASE_URL=postgres://user:pass@host:port/dbname
  OR individual variables:
  DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASSWORD

Trade table schema (create once on the server):
  CREATE TABLE trade (
      id      SERIAL PRIMARY KEY,
      user_id BIGINT NOT NULL,
      blob    BYTEA  NOT NULL
  );
"""
import json
import os

from utils.savers import build_inventory_blob
from parse.inventory import Inventory
from version import OPENBAR_ID, GREENLAMP_ID

# Bidirectional send-target mapping
USER_PAIR: dict[int, int] = {
    OPENBAR_ID:   GREENLAMP_ID,
    GREENLAMP_ID: OPENBAR_ID,
}

USER_NAMES: dict[int, str] = {
    OPENBAR_ID:   "Openbar",
    GREENLAMP_ID: "Greenlamp",
}


# ---------------------------------------------------------------------------
# .env loader (no python-dotenv dependency)
# ---------------------------------------------------------------------------

def _load_dotenv() -> None:
    """Minimal .env parser — loads variables into os.environ if not already set.

    Search order:
    1. Frozen (PyInstaller) exe  → same folder as the .exe
    2. Development               → project root (one level above utils/)
    """
    import sys as _sys
    if getattr(_sys, "frozen", False):
        # Running as a PyInstaller bundle: look next to the exe
        base_dir = os.path.dirname(_sys.executable)
    else:
        # Running from source: look at the project root
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    env_path = os.path.join(base_dir, ".env")
    if not os.path.exists(env_path):
        return
    with open(env_path, encoding="utf-8") as fh:
        for raw_line in fh:
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key   = key.strip()
            value = value.strip().strip('"').strip("'")
            if key not in os.environ:
                os.environ[key] = value


def _get_connection():
    """Return a live psycopg2 connection; raises RuntimeError if psycopg2 is absent."""
    _load_dotenv()
    try:
        import psycopg2  # noqa: PLC0415
    except ImportError as exc:
        raise RuntimeError(
            "psycopg2 is required for gift features.\n"
            "Run:  pip install psycopg2-binary"
        ) from exc

    url = os.environ.get("DATABASE_URL")
    if url:
        return psycopg2.connect(url)
    return psycopg2.connect(
        host    =os.environ.get("DB_HOST",     "localhost"),
        port    =int(os.environ.get("DB_PORT", "5432")),
        dbname  =os.environ.get("DB_NAME",     "mewgenics"),
        user    =os.environ.get("DB_USER",     ""),
        password=os.environ.get("DB_PASSWORD", ""),
    )


# ---------------------------------------------------------------------------
# Steam ID helpers
# ---------------------------------------------------------------------------

def get_steam_id_from_path(sav_path: str) -> int | None:
    """Extract the Steam ID embedded in the save path.

    Expected layout: …/Glaiel Games/Mewgenics/<SteamID>/saves/steamcampaign01.sav
    """
    try:
        parts = sav_path.replace("\\", "/").split("/")
        idx = next(i for i, p in enumerate(parts) if p.lower() == "saves")
        candidate = parts[idx - 1]
        if candidate.isdigit():
            return int(candidate)
    except (StopIteration, IndexError):
        pass
    return None


def get_recipient_id(my_steam_id: int) -> int | None:
    """Return the partner's Steam ID, or None if the ID is not in the known pair."""
    return USER_PAIR.get(my_steam_id)


def get_user_name(steam_id: int | None) -> str:
    """Return a human-readable name for the given Steam ID."""
    if steam_id is None:
        return "Unknown"
    return USER_NAMES.get(steam_id, str(steam_id))


# ---------------------------------------------------------------------------
# Item serialization / deserialization
# ---------------------------------------------------------------------------

def _normalize_raw(raw: dict) -> dict:
    """Fix the subname/subName key inconsistency before calling build_inventory_blob."""
    result = dict(raw)
    if "subname" in result and "subName" not in result:
        result["subName"] = result.pop("subname")
    return result


def serialize_item(raw_item: dict) -> str:
    return json.dumps(raw_item)


def deserialize_item(blob) -> dict | None:
    data = json.loads(blob)
    return data


# ---------------------------------------------------------------------------
# Remote DB operations
# ---------------------------------------------------------------------------

def send_gift(raw_item: dict, recipient_id: int) -> None:
    """Insert the serialized item into the trade table addressed to recipient_id."""
    import psycopg2  # noqa: PLC0415
    blob = serialize_item(raw_item)
    conn = _get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO trade (user_id, blob) VALUES (%s, %s)",
            (recipient_id, blob),
        )
        conn.commit()
    finally:
        conn.close()


def send_gifts_batch(raw_items: list[dict], recipient_id: int) -> None:
    """Insert multiple items into the trade table in a single transaction."""
    import psycopg2  # noqa: PLC0415
    conn = _get_connection()
    try:
        cur = conn.cursor()
        for raw in raw_items:
            blob = serialize_item(raw)
            cur.execute(
                "INSERT INTO trade (user_id, blob) VALUES (%s, %s)",
                (recipient_id, blob),
            )
        conn.commit()
    finally:
        conn.close()


def receive_gifts(my_steam_id: int) -> list[dict]:
    """Claim all pending rows for my_steam_id, delete them, and return raw items."""
    conn = _get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT id, blob FROM trade WHERE user_id = %s",
            (my_steam_id,),
        )
        rows = cur.fetchall()
        if not rows:
            return []

        ids   = [row[0] for row in rows]
        blobs = [row[1] for row in rows]

        cur.execute("DELETE FROM trade WHERE id = ANY(%s)", (ids,))
        conn.commit()

        items: list[dict] = []
        for blob in blobs:
            raw = deserialize_item(blob)
            if raw is not None:
                items.append(raw)
        return items
    finally:
        conn.close()

