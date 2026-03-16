"""
AppController — manages all application state and business logic.

No PySide6 imports here; this module is UI-agnostic.
"""
import datetime
import os

from parse.item import Item, GhostItem
from catalogs.itemcatalog import item_catalog
from utils.loaders import load_inventories, load_gold, load_tokens, load_items_pool
from utils.savers import save_inventories as _save_inventories, save_tokens, save_items_pool

# Rarities that should never appear in any view
EXCLUDED_RARITIES = {"sidequest", "quest"}


class AppController:
    """Owns app state; exposes query and command methods for the UI to call."""

    def __init__(self, sav_path: str):
        self.sav_path = sav_path
        self.loaded_mtime: float | None = None

        # Populated by load_data()
        self.inventories: dict = {}
        self.golds: int = 0
        self.tokens: dict = {}
        self.items_pool: dict = {}
        self.pool_items: list = []
        self.undiscovered_pool_items: list = []
        self.inv_items: dict = {}

    # ------------------------------------------------------------------
    # Data loading
    # ------------------------------------------------------------------

    def load_data(self):
        """Load (or reload) all data from the save file."""
        raw = load_inventories(self.sav_path)
        self.loaded_mtime = (
            os.path.getmtime(self.sav_path) if os.path.exists(self.sav_path) else None
        )
        self.inventories = {
            "storage": raw["storage"],
            "trash":   raw["trash"],
        }
        self.golds  = load_gold(self.sav_path)
        self.tokens = load_tokens(self.loaded_mtime)
        self.items_pool = load_items_pool()

        # Auto-add storage + trash items into the pool (never overwrite existing entries)
        changed = False
        for inv_key in ("storage", "trash"):
            for raw_item in self.inventories[inv_key].raws:
                name = raw_item.get("name")
                if name and name not in self.items_pool:
                    self.items_pool[name] = raw_item
                    changed = True
        if changed:
            save_items_pool(self.items_pool)

        self.pool_items = [Item(r) for r in self.items_pool.values()]

        discovered_names = set(self.items_pool.keys())
        all_catalog = item_catalog.get_all_non_quest_items()
        self.undiscovered_pool_items = [
            GhostItem(name, details)
            for name, details in all_catalog.items()
            if name not in discovered_names
            and details is not None
            and details.get("rarity") not in EXCLUDED_RARITIES
            and details.get("rarity") is not None
        ]

        self.inv_items = {
            "Storage": self.inventories["storage"].items,
            "Trash":   self.inventories["trash"].items,
            "Pool":    self.pool_items + self.undiscovered_pool_items,
        }

    # ------------------------------------------------------------------
    # Persistence helpers
    # ------------------------------------------------------------------

    def save_inventories(self):
        """Persist inventories to disk and refresh loaded_mtime."""
        _save_inventories(self.sav_path, self.inventories)
        try:
            self.loaded_mtime = os.path.getmtime(self.sav_path)
        except OSError:
            pass

    def get_save_date_str(self) -> str:
        """Return a human-readable last-modified timestamp for the save file."""
        try:
            mtime = os.path.getmtime(self.sav_path)
            dt    = datetime.datetime.fromtimestamp(mtime)
            return dt.strftime("💾 %Y-%m-%d  %H:%M:%S")
        except OSError:
            return "💾 —"

    def check_save_changed(self) -> tuple[bool, float | None, str]:
        """Return (has_changed, current_mtime, formatted_date_str).

        has_changed is True when the file on disk is newer than loaded_mtime.
        """
        try:
            current_mtime = os.path.getmtime(self.sav_path)
        except OSError:
            return False, None, ""

        if self.loaded_mtime is None or current_mtime == self.loaded_mtime:
            return False, current_mtime, ""

        dt = datetime.datetime.fromtimestamp(current_mtime)
        return True, current_mtime, dt.strftime("%Y-%m-%d  %H:%M:%S")

    # ------------------------------------------------------------------
    # Sacrifice — single item
    # ------------------------------------------------------------------

    def get_sacrifice_gains(self, inv_key: str, idx: int) -> dict[str, int]:
        """Return {rarity: 1} for the item at *idx* in *inv_key* (no side effects)."""
        item = self.inventories[inv_key].items[idx]
        r = item.rarity
        return {r: 1} if r in self.tokens else {}

    def apply_sacrifice_item(self, inv_key: str, idx: int):
        """Remove item, award its token, persist."""
        inventory = self.inventories[inv_key]
        rarity = inventory.items[idx].rarity
        del inventory.raws[idx]
        del inventory.items[idx]
        inventory.count -= 1
        if rarity in self.tokens:
            self.tokens[rarity] += 1
        self.save_inventories()
        save_tokens(self.tokens, self.loaded_mtime)

    # ------------------------------------------------------------------
    # Sacrifice — multiple items (storage)
    # ------------------------------------------------------------------

    def get_sacrifice_multiple_gains(self, storage_indices: list[int]) -> dict[str, int]:
        """Return {rarity: count} for a set of storage indices (no side effects)."""
        gains: dict[str, int] = {}
        inventory = self.inventories["storage"]
        for idx in storage_indices:
            r = inventory.items[idx].rarity
            if r in self.tokens:
                gains[r] = gains.get(r, 0) + 1
        return gains

    def apply_sacrifice_multiple(self, storage_indices: list[int]):
        """Remove items in reverse-index order, award tokens, persist."""
        inventory = self.inventories["storage"]
        for idx in sorted(storage_indices, reverse=True):
            rarity = inventory.items[idx].rarity
            if rarity in self.tokens:
                self.tokens[rarity] += 1
            del inventory.raws[idx]
            del inventory.items[idx]
            inventory.count -= 1
        self.save_inventories()
        save_tokens(self.tokens, self.loaded_mtime)

    # ------------------------------------------------------------------
    # Sacrifice — all non-broken trash items
    # ------------------------------------------------------------------

    def get_sacrifice_all_trash_gains(self) -> dict[str, int]:
        """Return {rarity: count} for all non-broken trash items (no side effects)."""
        gains: dict[str, int] = {}
        for item in self.inventories["trash"].items:
            if not getattr(item, "broken", False):
                r = item.rarity
                if r in self.tokens:
                    gains[r] = gains.get(r, 0) + 1
        return gains

    def apply_sacrifice_all_trash(self):
        """Remove non-broken trash items, award tokens, persist."""
        inventory = self.inventories["trash"]
        keep_raws, keep_items = [], []
        for raw, item in zip(inventory.raws, inventory.items):
            if getattr(item, "broken", False):
                keep_raws.append(raw)
                keep_items.append(item)
            else:
                if item.rarity in self.tokens:
                    self.tokens[item.rarity] += 1
        inventory.raws  = keep_raws
        inventory.items = keep_items
        inventory.count = len(keep_items)
        self.inv_items["Trash"] = inventory.items  # keep reference in sync
        self.save_inventories()
        save_tokens(self.tokens, self.loaded_mtime)

    # ------------------------------------------------------------------
    # Move item between storage ↔ trash
    # ------------------------------------------------------------------

    def apply_move_item(self, src_key: str, idx: int) -> str:
        """Move item from *src_key* inventory to the other. Returns destination key."""
        dst_key = "trash" if src_key == "storage" else "storage"
        src_inv = self.inventories[src_key]
        dst_inv = self.inventories[dst_key]

        raw = src_inv.raws[idx]
        del src_inv.raws[idx]
        del src_inv.items[idx]
        src_inv.count -= 1

        new_seq_id = max((r.get("seqId", 0) for r in dst_inv.raws), default=0) + 1
        new_raw = {**raw, "seqId": new_seq_id}
        dst_inv.raws.append(new_raw)
        dst_inv.items.append(Item(new_raw))
        dst_inv.count += 1

        self.save_inventories()
        return dst_key

    def apply_move_multiple_to_trash(self, storage_indices: list[int]):
        """Move multiple storage items to trash in reverse-index order, persist."""
        storage = self.inventories["storage"]
        trash   = self.inventories["trash"]
        for idx in sorted(storage_indices, reverse=True):
            raw = storage.raws[idx]
            del storage.raws[idx]
            del storage.items[idx]
            storage.count -= 1
            new_seq = max((r.get("seqId", 0) for r in trash.raws), default=0) + 1
            new_raw = {**raw, "seqId": new_seq}
            trash.raws.append(new_raw)
            trash.items.append(Item(new_raw))
            trash.count += 1
        self.save_inventories()

    # ------------------------------------------------------------------
    # Repair broken item (trash → storage)
    # ------------------------------------------------------------------

    REPAIR_COST = 3

    def get_repair_info(self, trash_idx: int) -> dict:
        """Return a dict with all data needed to build the repair confirmation dialog."""
        item      = self.inventories["trash"].items[trash_idx]
        rarity    = item.rarity
        available = self.tokens.get(rarity, 0)
        return {
            "rarity":       rarity,
            "cost":         self.REPAIR_COST,
            "available":    available,
            "can_afford":   available >= self.REPAIR_COST,
            "display_name": (item.details or {}).get("name_resolved") or item.name or "?",
        }

    def apply_repair_item(self, trash_idx: int):
        """Deduct repair tokens, move item to storage with sep_flag reset, persist."""
        inventory = self.inventories["trash"]
        rarity    = inventory.items[trash_idx].rarity
        self.tokens[rarity] -= self.REPAIR_COST

        raw = inventory.raws[trash_idx]
        del inventory.raws[trash_idx]
        del inventory.items[trash_idx]
        inventory.count -= 1

        storage    = self.inventories["storage"]
        new_seq_id = max((r.get("seqId", 0) for r in storage.raws), default=0) + 1
        repaired_raw = {**raw, "seqId": new_seq_id, "sep_flag": 1}
        storage.raws.append(repaired_raw)
        storage.items.append(Item(repaired_raw))
        storage.count += 1

        self.save_inventories()
        save_tokens(self.tokens, self.loaded_mtime)

    # ------------------------------------------------------------------
    # Clone pool item to storage (debug only)
    # ------------------------------------------------------------------

    def apply_clone_to_storage(self, pool_idx: int):
        """Clone the pool item at *pool_idx* into storage, persist."""
        original_raw = list(self.items_pool.values())[pool_idx]
        storage      = self.inventories["storage"]
        new_seq_id   = max((r.get("seqId", 0) for r in storage.raws), default=0) + 1
        new_raw      = {**original_raw, "seqId": new_seq_id}
        storage.raws.append(new_raw)
        storage.items.append(Item(new_raw))
        storage.count += 1
        self.save_inventories()

    # ------------------------------------------------------------------
    # Gift — send / receive via remote PostgreSQL
    # ------------------------------------------------------------------

    def get_gift_context(self) -> dict:
        """Return a dict describing the current user's gift context.

        Keys: my_id, recipient_id, my_name, recipient_name, is_known_user
        """
        from utils.gift_manager import get_steam_id_from_path, get_recipient_id, get_user_name
        my_id        = get_steam_id_from_path(self.sav_path)
        recipient_id = get_recipient_id(my_id) if my_id is not None else None
        return {
            "my_id":          my_id,
            "recipient_id":   recipient_id,
            "my_name":        get_user_name(my_id),
            "recipient_name": get_user_name(recipient_id),
            "is_known_user":  my_id is not None and recipient_id is not None,
        }

    def apply_send_gift(self, inv_key: str, idx: int) -> None:
        """Serialize item, post it to the remote DB for the partner, remove locally."""
        from utils.gift_manager import send_gift
        ctx = self.get_gift_context()
        if not ctx["is_known_user"]:
            raise ValueError("Cannot determine gift recipient — save file user ID not recognized.")

        inventory = self.inventories[inv_key]
        raw       = inventory.raws[idx]

        send_gift(raw, ctx["recipient_id"])

        del inventory.raws[idx]
        del inventory.items[idx]
        inventory.count -= 1
        self.save_inventories()

    def apply_receive_gifts(self) -> list[dict]:
        """Fetch all pending gifts, add them to storage, persist. Returns the raw items."""
        from utils.gift_manager import receive_gifts, get_steam_id_from_path
        my_id = get_steam_id_from_path(self.sav_path)
        if my_id is None:
            return []

        raw_items = receive_gifts(my_id)
        if not raw_items:
            return []

        storage = self.inventories["storage"]
        for raw in raw_items:
            new_seq_id = max((r.get("seqId", 0) for r in storage.raws), default=0) + 1
            new_raw    = {**raw, "seqId": new_seq_id}
            # Normalize subname key so it round-trips correctly
            if "subname" in new_raw and "subName" not in new_raw:
                new_raw["subName"] = new_raw.pop("subname")
            storage.raws.append(new_raw)
            storage.items.append(Item(new_raw))
            storage.count += 1

        self.save_inventories()
        return raw_items

