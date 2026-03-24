"""
AppController — manages all application state and business logic.

No PySide6 imports here; this module is UI-agnostic.
"""
import datetime
import os
from typing import Optional

from parse.cat import Cat
from parse.item import Item, GhostItem
from catalogs.itemcatalog import item_catalog
from utils.loaders import load_inventories, load_gold, load_tokens, load_items_pool, \
    load_save_properties, load_cats_count, load_bank_inventory, load_bank_folders, SAVE_INFO_KEYS, \
    load_house_state_raw, load_adventure_keys, load_cats, load_pedigree, \
    load_current_day, load_cat_bank, load_newborn_kills
from utils.savers import save_inventories as _save_inventories, save_tokens, \
    save_bank_inventory, save_items_pool, save_bank_folders, save_house_state, \
    save_cat_bank, save_new_cat, save_newborn_kills, save_gold as _save_gold

# Rarities that should never appear in any view
EXCLUDED_RARITIES = {"sidequest", "quest"}

# Item names that should never be tracked in the pool nor offered in lootboxes
POOL_NAME_BLACKLIST: frozenset = frozenset({
    "SoulJar_Full",
})


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
        self.save_properties: dict[str, str] = {}
        self.bank_folders: dict = {"folders": [], "item_folders": {}}
        self.cats: list = []
        # Cat bank (maps db_key → {'entry_bytes': bytes, 'room_name': str})
        self.cat_bank: dict = {}
        # house_state round-trip helpers (set by load_data / apply_bank_cat / apply_unbank_cat)
        self._house_state_prefix:  bytes = b'\x00\x00\x00\x00'
        self._house_state_entries: dict  = {}  # {cat_key: raw_entry_bytes} currently in house_state
        self._house_state_info:    dict  = {}  # {cat_key: room_name} mirror for room lookups
        self.newborn_kill_count:   int   = 0

    # ------------------------------------------------------------------
    # Data loading
    # ------------------------------------------------------------------

    def load_data(self):
        """Load (or reload) all item/token/gold data from the save file.

        Cat data is intentionally **not** loaded here — call
        ``load_cats_data()`` separately when the Cat Manager is opened.
        This keeps startup fast for users who only manage items.
        """
        raw = load_inventories(self.sav_path)
        self.loaded_mtime = (
            os.path.getmtime(self.sav_path) if os.path.exists(self.sav_path) else None
        )
        self.inventories = {
            "storage": raw["storage"],
            "trash":   raw["trash"],
            "bank":    load_bank_inventory(self.sav_path),
        }
        self.golds  = load_gold(self.sav_path)
        self.tokens = load_tokens(self.sav_path)
        self.items_pool = load_items_pool()
        self.bank_folders = load_bank_folders(self.sav_path)
        self.save_properties = load_save_properties(self.sav_path, SAVE_INFO_KEYS)
        self.save_properties["_cats_count"] = str(load_cats_count(self.sav_path))

        # Auto-add storage + trash items into the pool (never overwrite existing entries)
        changed = False
        for inv_key in ("storage", "trash"):
            for raw_item in self.inventories[inv_key].raws:
                name = raw_item.get("name")
                if name and name not in self.items_pool and name not in POOL_NAME_BLACKLIST:
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
            "Bank":    self.inventories["bank"].items,
            "Pool":    self.pool_items + self.undiscovered_pool_items,
        }

        # Cats are NOT loaded here — call load_cats_data() on demand.
        self.cats = []

    # ------------------------------------------------------------------
    # Cat data loading (on-demand — called by Cat Manager only)
    # ------------------------------------------------------------------

    def load_cats_data(self):
        """Parse all cats from the save file and resolve relationships.

        This is intentionally separated from ``load_data()`` because LZ4
        decompression of every cat blob is slow and unnecessary when the user
        only wants to manage items.  ``CatManagerWindow`` calls this method
        just before it is displayed.
        """
        adv      = load_adventure_keys(self.sav_path)
        raw_cats = load_cats(self.sav_path)

        # Load house_state for both Cat init (house_info) and round-trip (entries)
        hs_prefix, house, hs_entries = load_house_state_raw(self.sav_path)
        self._house_state_prefix  = hs_prefix
        self._house_state_entries = hs_entries
        self._house_state_info    = dict(house)

        self.cat_bank           = load_cat_bank(self.sav_path)
        ped_map                 = load_pedigree(self.sav_path)
        current_day             = load_current_day(self.sav_path)
        self.newborn_kill_count = load_newborn_kills(self.sav_path)

        cats: list = []
        for key, blob in raw_cats:
            try:
                cats.append(Cat(blob, key, house, adv, current_day))
            except Exception:
                pass

        key_to_cat: dict = {c.db_key: c for c in cats}

        for cat in cats:
            pa: Optional[Cat] = None
            pb: Optional[Cat] = None
            if cat.db_key in ped_map:
                pa_k, pb_k = ped_map[cat.db_key]
                pa = key_to_cat.get(pa_k)
                pb = key_to_cat.get(pb_k)
                if pa is cat: pa = None
                if pb is cat: pb = None
            cat.parent_a = pa
            cat.parent_b = pb

            cat.lovers = []
            for key in getattr(cat, "_lover_uids", []):
                other = key_to_cat.get(key)
                if other is not None and other is not cat and other not in cat.lovers:
                    cat.lovers.append(other)

            cat.haters = []
            for key in getattr(cat, "_hater_uids", []):
                other = key_to_cat.get(key)
                if other is not None and other is not cat and other not in cat.haters:
                    cat.haters.append(other)

        # Build children bottom-up
        for cat in cats:
            cat.children = []
        for cat in cats:
            for parent in (cat.parent_a, cat.parent_b):
                if parent is not None and cat not in parent.children:
                    parent.children.append(cat)

        # Compute generation depth (iterative, handles cycles)
        for c in cats:
            c.generation = 0 if (c.parent_a is None and c.parent_b is None) else -1

        for _ in range(len(cats) + 1):
            changed = False
            for c in cats:
                pa_g = c.parent_a.generation if c.parent_a is not None else -1
                pb_g = c.parent_b.generation if c.parent_b is not None else -1
                if pa_g >= 0 or pb_g >= 0:
                    g = max(pa_g, pb_g) + 1
                    if c.generation != g:
                        c.generation = g
                        changed = True
            if not changed:
                break

        for c in cats:
            if c.generation < 0:
                c.generation = 0

        # Mark cats that are in the cat bank
        for cat in cats:
            if cat.db_key in self.cat_bank:
                cat.status = "In Bank"
                cat.room   = self.cat_bank[cat.db_key].get('room_name', '')

        self.cats = cats





    # ------------------------------------------------------------------
    # Persistence helpers
    # ------------------------------------------------------------------

    def save_inventories(self):
        """Persist inventories to disk and refresh loaded_mtime."""
        _save_inventories(self.sav_path, self.inventories)
        save_bank_inventory(self.sav_path, self.inventories["bank"])
        self._refresh_mtime()

    # ------------------------------------------------------------------
    # Cat rename
    # ------------------------------------------------------------------

    def apply_rename_cat(self, cat, new_name: str) -> None:
        """Rename *cat* in-place, write its blob back to the save file."""
        from utils.savers import save_cat
        cat.rename_in_blob(new_name)
        save_cat(self.sav_path, cat)
        self._refresh_mtime()

    # ------------------------------------------------------------------
    # Cat bank — move cats between the house and the cat bank
    # ------------------------------------------------------------------

    def apply_bank_cat(self, cat) -> None:
        """Remove *cat* from the house and place it in the cat bank.

        The cat's raw house_state entry bytes are preserved so that
        ``apply_unbank_cat`` can restore it exactly to the same room.
        Only cats with status ``"In House"`` can be banked.
        """
        if cat.status != "In House":
            raise ValueError(
                f"Only cats that are 'In House' can be banked "
                f"('{cat.name}' is currently '{cat.status}')."
            )

        entry_bytes = self._house_state_entries.get(cat.db_key)
        if entry_bytes is None:
            raise ValueError(
                f"Could not find '{cat.name}' in house_state — "
                f"the save file may have been modified externally."
            )

        # Store in cat bank
        self.cat_bank[cat.db_key] = {
            'entry_bytes': entry_bytes,
            'room_name':   cat.room,
        }
        # Remove from active house_state entries
        self._house_state_entries.pop(cat.db_key, None)

        # Persist both
        save_house_state(self.sav_path, self._house_state_prefix, self._house_state_entries)
        save_cat_bank(self.sav_path, self.cat_bank)

        # Update in-memory cat
        cat.status = "In Bank"
        cat.room   = self.cat_bank[cat.db_key]['room_name']

        self._refresh_mtime()

    def apply_unbank_cat(self, cat) -> None:
        """Return *cat* from the cat bank back to the house.

        Restores its original house_state entry bytes verbatim so it
        appears in the same room it occupied before banking.
        Only cats with status ``"In Bank"`` can be unbanked.
        """
        if cat.status != "In Bank":
            raise ValueError(
                f"Only banked cats can be moved back to the house "
                f"('{cat.name}' is currently '{cat.status}')."
            )
        if cat.db_key not in self.cat_bank:
            raise ValueError(
                f"Cat '{cat.name}' (key={cat.db_key}) not found in cat bank data."
            )

        bank_entry = self.cat_bank[cat.db_key]
        entry_bytes = bank_entry['entry_bytes']
        room_name   = bank_entry['room_name']

        # Restore to active house_state entries
        self._house_state_entries[cat.db_key] = entry_bytes

        # Remove from cat bank
        del self.cat_bank[cat.db_key]

        # Persist both
        save_house_state(self.sav_path, self._house_state_prefix, self._house_state_entries)
        save_cat_bank(self.sav_path, self.cat_bank)

        # Update in-memory cat
        cat.status = "In House"
        cat.room   = room_name

        self._refresh_mtime()

    # ------------------------------------------------------------------
    # Cat gifts — send / receive via remote PostgreSQL
    # ------------------------------------------------------------------

    def apply_send_cat(self, cat) -> None:
        """Send *cat* to the partner via the ``cat_trade`` PostgreSQL table.

        The cat blob is uploaded as-is.  Locally the cat is removed from
        ``house_state`` (if In House) or ``cat_bank`` (if In Bank) and its
        status is set to ``"Gone"``.  The row in the ``cats`` table is kept
        so that pedigree data remains intact.

        Only cats with status ``"In House"`` or ``"In Bank"`` can be sent.
        """
        from utils.gift_manager import send_cat as _send_cat, get_steam_id_from_path, get_recipient_id

        if cat.status not in ("In House", "In Bank"):
            raise ValueError(
                f"Only cats that are 'In House' or 'In Bank' can be sent "
                f"('{cat.name}' is currently '{cat.status}')."
            )

        ctx_id    = get_steam_id_from_path(self.sav_path)
        recipient = get_recipient_id(ctx_id) if ctx_id is not None else None
        if recipient is None:
            raise ValueError(
                "Cannot determine gift recipient — save file user ID not recognized."
            )

        # Strip genealogy tree before sending (age will be set by the recipient)
        current_day = int(self.save_properties.get("current_day") or 0)
        cat.strip_genealogy(current_day, patch_age=False)

        # Upload the blob
        _send_cat(cat.to_blob(), recipient)

        # Remove from local tracking
        if cat.status == "In House":
            self._house_state_entries.pop(cat.db_key, None)
            save_house_state(self.sav_path, self._house_state_prefix, self._house_state_entries)
        elif cat.status == "In Bank":
            self.cat_bank.pop(cat.db_key, None)
            save_cat_bank(self.sav_path, self.cat_bank)

        cat.status = "Gone"
        cat.room   = ""
        self._refresh_mtime()

    def apply_bank_cats_multiple(self, cats: list) -> int:
        """Bank multiple "In House" cats in a single write. Returns count banked."""
        banked = 0
        for cat in cats:
            if cat.status != "In House":
                continue
            entry_bytes = self._house_state_entries.get(cat.db_key)
            if entry_bytes is None:
                continue
            self.cat_bank[cat.db_key] = {
                'entry_bytes': entry_bytes,
                'room_name':   cat.room,
            }
            self._house_state_entries.pop(cat.db_key, None)
            cat.status = "In Bank"
            banked += 1
        if banked:
            save_house_state(self.sav_path, self._house_state_prefix, self._house_state_entries)
            save_cat_bank(self.sav_path, self.cat_bank)
            self._refresh_mtime()
        return banked

    def apply_unbank_cats_multiple(self, cats: list) -> int:
        """Unbank multiple "In Bank" cats in a single write. Returns count unbanked."""
        unbanked = 0
        for cat in cats:
            if cat.status != "In Bank" or cat.db_key not in self.cat_bank:
                continue
            bank_entry = self.cat_bank[cat.db_key]
            self._house_state_entries[cat.db_key] = bank_entry['entry_bytes']
            cat.status = "In House"
            cat.room   = bank_entry['room_name']
            del self.cat_bank[cat.db_key]
            unbanked += 1
        if unbanked:
            save_house_state(self.sav_path, self._house_state_prefix, self._house_state_entries)
            save_cat_bank(self.sav_path, self.cat_bank)
            self._refresh_mtime()
        return unbanked

    # ------------------------------------------------------------------
    # Cat room management & newborn deletion
    # ------------------------------------------------------------------

    def get_available_rooms(self) -> list[str]:
        """Return sorted list of unique room names from the current house state."""
        rooms = {r for r in self._house_state_info.values() if r}
        return sorted(rooms)

    @staticmethod
    def _rebuild_cat_entry_bytes(entry: bytes, cat_key: int, new_room: str) -> bytes:
        """Return a new house_state entry with *new_room*, preserving unknown fields."""
        import struct as _struct
        unk1         = _struct.unpack_from('<I', entry, 4)[0]  if len(entry) >= 8  else 0
        old_room_len = _struct.unpack_from('<I', entry, 8)[0]  if len(entry) >= 12 else 0
        unk2         = _struct.unpack_from('<I', entry, 12)[0] if len(entry) >= 16 else 0
        tail_start   = 16 + old_room_len
        tail = entry[tail_start:tail_start + 24] if len(entry) >= tail_start + 24 else b'\x00' * 24
        room_enc = new_room.encode('ascii', errors='replace')
        return (
            _struct.pack('<II', cat_key, unk1)
            + _struct.pack('<II', len(room_enc), unk2)
            + room_enc
            + tail
        )

    def apply_move_cat_room(self, cat, new_room: str) -> None:
        """Move an In-House cat to *new_room* by rewriting its house_state entry."""
        if cat.status != "In House":
            raise ValueError(
                f"Only 'In House' cats can be moved to a room "
                f"('{cat.name}' is '{cat.status}')."
            )
        entry = self._house_state_entries.get(cat.db_key)
        if entry is None:
            raise ValueError(f"No house_state entry for '{cat.name}'.")
        new_entry = self._rebuild_cat_entry_bytes(entry, cat.db_key, new_room)
        self._house_state_entries[cat.db_key] = new_entry
        self._house_state_info[cat.db_key]    = new_room
        cat.room = new_room
        save_house_state(self.sav_path, self._house_state_prefix, self._house_state_entries)
        self._refresh_mtime()

    def apply_move_cats_room_multiple(self, cats: list, new_room: str) -> int:
        """Move multiple In-House cats to *new_room* in a single write.

        Silently skips cats that are not In House.
        Returns the number of cats actually moved.
        """
        moved = 0
        for cat in cats:
            if cat.status != "In House":
                continue
            entry = self._house_state_entries.get(cat.db_key)
            if entry is None:
                continue
            new_entry = self._rebuild_cat_entry_bytes(entry, cat.db_key, new_room)
            self._house_state_entries[cat.db_key] = new_entry
            self._house_state_info[cat.db_key]    = new_room
            cat.room = new_room
            moved += 1
        if moved:
            save_house_state(self.sav_path, self._house_state_prefix, self._house_state_entries)
            self._refresh_mtime()
        return moved

    def apply_delete_cat(self, cat) -> tuple[int, int]:
        """Mark *cat* as gone (newborn trash).

        The row in the ``cats`` table is **never deleted** so pedigree data
        remains intact.  The cat is only removed from ``house_state`` /
        ``cat_bank`` tracking (which makes it appear as ``"Gone"`` on the next
        load), and its in-memory ``status`` is set to ``"Gone"`` immediately.

        Updates the newborn-kill counter and awards 25 gold for every 10 kills.
        Returns ``(new_kill_count, gold_awarded)``.
        """
        if cat.status == "In House":
            self._house_state_entries.pop(cat.db_key, None)
            self._house_state_info.pop(cat.db_key, None)
            save_house_state(self.sav_path, self._house_state_prefix, self._house_state_entries)
        elif cat.status == "In Bank":
            self.cat_bank.pop(cat.db_key, None)
            save_cat_bank(self.sav_path, self.cat_bank)

        # Mark gone in memory — row stays in the cats table
        cat.status = "Gone"
        cat.room   = ""

        self.newborn_kill_count += 1
        gold_awarded = 0
        if self.newborn_kill_count % 10 == 0:
            gold_awarded = 25
            self.golds += gold_awarded
            _save_gold(self.sav_path, self.golds)

        save_newborn_kills(self.sav_path, self.newborn_kill_count)
        self._refresh_mtime()
        return self.newborn_kill_count, gold_awarded

    def apply_delete_cats_multiple(self, cats: list) -> tuple[int, int]:
        """Mark multiple cats as gone (newborn trash).

        Like ``apply_delete_cat``, no rows are deleted from the ``cats`` table.
        Returns ``(n_deleted, total_gold_awarded)``.
        """
        if not cats:
            return 0, 0
        hs_changed   = False
        bank_changed = False
        total_gold   = 0

        for cat in cats:
            if cat.status == "In House":
                self._house_state_entries.pop(cat.db_key, None)
                self._house_state_info.pop(cat.db_key, None)
                hs_changed = True
            elif cat.status == "In Bank":
                self.cat_bank.pop(cat.db_key, None)
                bank_changed = True
            # Mark gone in memory — row stays in the cats table
            cat.status = "Gone"
            cat.room   = ""
            self.newborn_kill_count += 1
            if self.newborn_kill_count % 10 == 0:
                total_gold += 25

        if hs_changed:
            save_house_state(self.sav_path, self._house_state_prefix, self._house_state_entries)
        if bank_changed:
            save_cat_bank(self.sav_path, self.cat_bank)
        if total_gold:
            self.golds += total_gold
            _save_gold(self.sav_path, self.golds)

        save_newborn_kills(self.sav_path, self.newborn_kill_count)
        self._refresh_mtime()
        return len(cats), total_gold

    def apply_send_cats_multiple(self, cats: list) -> int:
        """Send multiple cats as gifts in one batch. Returns count sent."""
        from utils.gift_manager import send_cat as _send_cat, get_steam_id_from_path, get_recipient_id
        sendable = [c for c in cats if c.status in ("In House", "In Bank")]
        if not sendable:
            return 0
        ctx_id    = get_steam_id_from_path(self.sav_path)
        recipient = get_recipient_id(ctx_id) if ctx_id is not None else None
        if recipient is None:
            raise ValueError("Cannot determine gift recipient — save file user ID not recognized.")
        hs_changed   = False
        bank_changed = False
        current_day  = int(self.save_properties.get("current_day") or 0)
        for cat in sendable:
            cat.strip_genealogy(current_day, patch_age=False)
            _send_cat(cat.to_blob(), recipient)
            if cat.status == "In House":
                self._house_state_entries.pop(cat.db_key, None)
                hs_changed = True
            elif cat.status == "In Bank":
                self.cat_bank.pop(cat.db_key, None)
                bank_changed = True
            cat.status = "Gone"
            cat.room   = ""
        if hs_changed:
            save_house_state(self.sav_path, self._house_state_prefix, self._house_state_entries)
        if bank_changed:
            save_cat_bank(self.sav_path, self.cat_bank)
        self._refresh_mtime()
        return len(sendable)

    def apply_receive_cats(self) -> list:
        """Fetch all pending cat blobs from ``cat_trade``, insert them into the
        local ``cats`` table, and place them in the cat bank so the user can
        move them to the house whenever ready.

        Returns the list of newly parsed ``Cat`` objects (status = ``"In Bank"``).
        """
        import struct
        from utils.gift_manager import receive_cats as _receive_cats, get_steam_id_from_path
        from parse.cat import Cat

        my_id = get_steam_id_from_path(self.sav_path)
        if my_id is None:
            return []

        blobs = _receive_cats(my_id)
        if not blobs:
            return []

        received: list = []
        receiver_day = int(self.save_properties.get("current_day") or 0)
        for blob in blobs:
            # Patch age to 2 using the receiver's current_day before saving
            try:
                tmp_cat = Cat(blob, 0, {}, set(), None)
                tmp_cat.strip_genealogy(receiver_day, patch_age=True)
                patched_blob = tmp_cat.to_blob()
            except Exception:
                patched_blob = blob  # fallback: use original blob as-is

            # Allocate a new db_key and persist the (age-patched) cat blob
            new_key = save_new_cat(self.sav_path, patched_blob)

            # Build a minimal house_state entry so the cat can be unbanked later.
            # Format (40 bytes): [u32 cat_key][u32 0][u32 room_len=0][u32 0][24×0x00]
            entry_bytes = (
                struct.pack('<II', new_key, 0)
                + struct.pack('<II', 0, 0)
                + b'\x00' * 24
            )

            # Register in cat bank
            self.cat_bank[new_key] = {
                'entry_bytes': entry_bytes,
                'room_name':   '',
            }

            # Parse the cat so it appears in the Cat Manager immediately
            try:
                cat = Cat(patched_blob, new_key, {}, set(), receiver_day)
                cat.status = "In Bank"
                cat.room   = ""
                self.cats.append(cat)
                received.append(cat)
            except Exception:
                pass  # blob unreadable — still saved on disk, will appear after next full reload

        save_cat_bank(self.sav_path, self.cat_bank)
        self._refresh_mtime()
        return received

    def _refresh_mtime(self):
        """Update loaded_mtime to the current file mtime (call after every write)."""
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
        save_tokens(self.sav_path, self.tokens)
        self._refresh_mtime()

    # ------------------------------------------------------------------
    # Sacrifice — multiple items (storage)
    # ------------------------------------------------------------------

    def get_sacrifice_multiple_gains(self, indices: list[int], inv_key: str = "storage") -> dict[str, int]:
        """Return {rarity: count} for a set of indices in *inv_key* (no side effects)."""
        gains: dict[str, int] = {}
        inventory = self.inventories[inv_key]
        for idx in indices:
            r = inventory.items[idx].rarity
            if r in self.tokens:
                gains[r] = gains.get(r, 0) + 1
        return gains

    def apply_sacrifice_multiple(self, indices: list[int], inv_key: str = "storage"):
        """Remove items in reverse-index order from *inv_key*, award tokens, persist."""
        inventory = self.inventories[inv_key]
        for idx in sorted(indices, reverse=True):
            rarity = inventory.items[idx].rarity
            if rarity in self.tokens:
                self.tokens[rarity] += 1
            del inventory.raws[idx]
            del inventory.items[idx]
            inventory.count -= 1
        self.save_inventories()
        save_tokens(self.sav_path, self.tokens)
        self._refresh_mtime()

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
        save_tokens(self.sav_path, self.tokens)
        self._refresh_mtime()

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

    def apply_move_multiple_to_storage(self, src_key: str, indices: list[int]):
        """Move multiple items from *src_key* inventory to storage in reverse-index order, persist."""
        src     = self.inventories[src_key]
        storage = self.inventories["storage"]
        for idx in sorted(indices, reverse=True):
            raw = src.raws[idx]
            del src.raws[idx]
            del src.items[idx]
            src.count -= 1
            new_seq = max((r.get("seqId", 0) for r in storage.raws), default=0) + 1
            new_raw = {**raw, "seqId": new_seq}
            storage.raws.append(new_raw)
            storage.items.append(Item(new_raw))
            storage.count += 1
        self.save_inventories()

    # ------------------------------------------------------------------
    # Bank — move items between storage ↔ bank
    # ------------------------------------------------------------------

    def apply_move_to_bank(self, storage_idx: int):
        """Move item at *storage_idx* from storage to the bank, persist.

        Also adds the item to items_pool if it has not been discovered yet,
        following the same rules as load_data().
        """
        storage = self.inventories["storage"]
        bank    = self.inventories["bank"]

        raw = storage.raws[storage_idx]
        del storage.raws[storage_idx]
        del storage.items[storage_idx]
        storage.count -= 1

        new_seq = max((r.get("seqId", 0) for r in bank.raws), default=0) + 1
        new_raw = {**raw, "seqId": new_seq}
        bank.raws.append(new_raw)
        bank.items.append(Item(new_raw))
        bank.count += 1

        self.save_inventories()

        # ── Pool auto-discovery (same rule as load_data) ──────────────
        name = new_raw.get("name")
        if name and name not in self.items_pool and name not in POOL_NAME_BLACKLIST:
            self.items_pool[name] = new_raw
            save_items_pool(self.items_pool)
            self.pool_items = [Item(r) for r in self.items_pool.values()]
            discovered_names = set(self.items_pool.keys())
            all_catalog = item_catalog.get_all_non_quest_items()
            self.undiscovered_pool_items = [
                GhostItem(n, details)
                for n, details in all_catalog.items()
                if n not in discovered_names
                and details is not None
                and details.get("rarity") not in EXCLUDED_RARITIES
                and details.get("rarity") is not None
            ]
            self.inv_items["Pool"] = self.pool_items + self.undiscovered_pool_items

    def apply_move_multiple_to_bank(self, src_key: str, indices: list[int]):
        """Move multiple items from *src_key* inventory to the bank in reverse-index order, persist."""
        src  = self.inventories[src_key]
        bank = self.inventories["bank"]
        for idx in sorted(indices, reverse=True):
            raw = src.raws[idx]
            del src.raws[idx]
            del src.items[idx]
            src.count -= 1
            new_seq = max((r.get("seqId", 0) for r in bank.raws), default=0) + 1
            new_raw = {**raw, "seqId": new_seq}
            bank.raws.append(new_raw)
            bank.items.append(Item(new_raw))
            bank.count += 1
            name = new_raw.get("name")
            if name and name not in self.items_pool and name not in POOL_NAME_BLACKLIST:
                self.items_pool[name] = new_raw
        self.save_inventories()
        save_items_pool(self.items_pool)
        self.pool_items = [Item(r) for r in self.items_pool.values()]
        discovered_names = set(self.items_pool.keys())
        all_catalog = item_catalog.get_all_non_quest_items()
        self.undiscovered_pool_items = [
            GhostItem(n, details)
            for n, details in all_catalog.items()
            if n not in discovered_names
            and details is not None
            and details.get("rarity") not in EXCLUDED_RARITIES
            and details.get("rarity") is not None
        ]
        self.inv_items["Pool"] = self.pool_items + self.undiscovered_pool_items

    def apply_move_from_bank(self, bank_idx: int):
        """Move item at *bank_idx* from the bank back to storage, persist."""
        bank    = self.inventories["bank"]
        storage = self.inventories["storage"]

        raw    = bank.raws[bank_idx]
        seq_id = str(raw.get("seqId", ""))
        self.bank_folders["item_folders"].pop(seq_id, None)

        del bank.raws[bank_idx]
        del bank.items[bank_idx]
        bank.count -= 1

        new_seq = max((r.get("seqId", 0) for r in storage.raws), default=0) + 1
        new_raw = {**raw, "seqId": new_seq}
        storage.raws.append(new_raw)
        storage.items.append(Item(new_raw))
        storage.count += 1

        self.save_inventories()
        save_bank_folders(self.sav_path, self.bank_folders)
        self._refresh_mtime()

    def apply_move_multiple_from_bank(self, indices: list[int]):
        """Move multiple bank items back to storage in reverse-index order, persist."""
        bank    = self.inventories["bank"]
        storage = self.inventories["storage"]
        for idx in sorted(indices, reverse=True):
            raw    = bank.raws[idx]
            seq_id = str(raw.get("seqId", ""))
            self.bank_folders["item_folders"].pop(seq_id, None)
            del bank.raws[idx]
            del bank.items[idx]
            bank.count -= 1
            new_seq = max((r.get("seqId", 0) for r in storage.raws), default=0) + 1
            new_raw = {**raw, "seqId": new_seq}
            storage.raws.append(new_raw)
            storage.items.append(Item(new_raw))
            storage.count += 1
        self.save_inventories()
        save_bank_folders(self.sav_path, self.bank_folders)
        self._refresh_mtime()

    def apply_move_bank_item_to_trash(self, bank_idx: int):
        """Move item at *bank_idx* from the bank to the trash, persist."""
        bank  = self.inventories["bank"]
        trash = self.inventories["trash"]

        raw    = bank.raws[bank_idx]
        seq_id = str(raw.get("seqId", ""))
        self.bank_folders["item_folders"].pop(seq_id, None)

        del bank.raws[bank_idx]
        del bank.items[bank_idx]
        bank.count -= 1

        new_seq = max((r.get("seqId", 0) for r in trash.raws), default=0) + 1
        new_raw = {**raw, "seqId": new_seq}
        trash.raws.append(new_raw)
        trash.items.append(Item(new_raw))
        trash.count += 1

        self.save_inventories()
        save_bank_folders(self.sav_path, self.bank_folders)
        self._refresh_mtime()

    def apply_move_multiple_bank_to_trash(self, indices: list[int]):
        """Move multiple bank items to trash in reverse-index order, persist."""
        bank  = self.inventories["bank"]
        trash = self.inventories["trash"]
        for idx in sorted(indices, reverse=True):
            raw    = bank.raws[idx]
            seq_id = str(raw.get("seqId", ""))
            self.bank_folders["item_folders"].pop(seq_id, None)
            del bank.raws[idx]
            del bank.items[idx]
            bank.count -= 1
            new_seq = max((r.get("seqId", 0) for r in trash.raws), default=0) + 1
            new_raw = {**raw, "seqId": new_seq}
            trash.raws.append(new_raw)
            trash.items.append(Item(new_raw))
            trash.count += 1
        self.save_inventories()
        save_bank_folders(self.sav_path, self.bank_folders)
        self._refresh_mtime()

    # ------------------------------------------------------------------
    # Bank — folder management
    # ------------------------------------------------------------------

    def get_bank_subfolders(self, parent_id) -> list:
        """Return folders whose parent_id matches (None = root)."""
        return [f for f in self.bank_folders["folders"] if f.get("parent_id") == parent_id]

    def get_bank_folder_by_id(self, folder_id: str) -> dict | None:
        for f in self.bank_folders["folders"]:
            if f["id"] == folder_id:
                return f
        return None

    def get_bank_folder_parent(self, folder_id: str):
        """Return parent_id of a folder, or None if it is at root."""
        f = self.get_bank_folder_by_id(folder_id)
        return f.get("parent_id") if f else None

    def get_bank_items_in_folder(self, folder_id) -> list[tuple[int, Item]]:
        """Return [(bank_inventory_index, Item)] for items in *folder_id* (None = root)."""
        result = []
        for i, item in enumerate(self.inventories["bank"].items):
            mapped = self.bank_folders["item_folders"].get(str(item.seqId))
            if mapped == folder_id:
                result.append((i, item))
        return result

    def get_bank_folder_path(self, folder_id) -> list[dict]:
        """Return list of folder dicts from root to *folder_id* (inclusive)."""
        path = []
        fid  = folder_id
        while fid is not None:
            f = self.get_bank_folder_by_id(fid)
            if f is None:
                break
            path.append(f)
            fid = f.get("parent_id")
        path.reverse()
        return path

    def is_bank_folder_ancestor(self, ancestor_id: str, descendant_id) -> bool:
        """Return True if ancestor_id is an ancestor of descendant_id."""
        fid = descendant_id
        while fid is not None:
            if fid == ancestor_id:
                return True
            f = self.get_bank_folder_by_id(fid)
            fid = f.get("parent_id") if f else None
        return False

    def create_bank_folder(self, name: str, parent_id) -> str:
        """Create a new folder under *parent_id*, return its id."""
        import uuid
        folder_id = str(uuid.uuid4())[:8]
        self.bank_folders["folders"].append({
            "id":        folder_id,
            "name":      name,
            "parent_id": parent_id,
        })
        save_bank_folders(self.sav_path, self.bank_folders)
        self._refresh_mtime()
        return folder_id

    def rename_bank_folder(self, folder_id: str, new_name: str):
        for f in self.bank_folders["folders"]:
            if f["id"] == folder_id:
                f["name"] = new_name
                break
        save_bank_folders(self.sav_path, self.bank_folders)
        self._refresh_mtime()

    def delete_bank_folder(self, folder_id: str):
        """Delete folder (and sub-folders); move all contained items to root."""
        def _collect(fid):
            ids = {fid}
            for f in self.bank_folders["folders"]:
                if f.get("parent_id") == fid:
                    ids |= _collect(f["id"])
            return ids
        all_ids = _collect(folder_id)
        for seq_id, fid in list(self.bank_folders["item_folders"].items()):
            if fid in all_ids:
                self.bank_folders["item_folders"][seq_id] = None
        self.bank_folders["folders"] = [
            f for f in self.bank_folders["folders"] if f["id"] not in all_ids
        ]
        save_bank_folders(self.sav_path, self.bank_folders)
        self._refresh_mtime()

    def move_bank_item_to_folder(self, seq_id: int, folder_id):
        """Assign bank item (by seqId) to *folder_id* (None = root)."""
        self.bank_folders["item_folders"][str(seq_id)] = folder_id
        save_bank_folders(self.sav_path, self.bank_folders)
        self._refresh_mtime()

    def move_bank_folder_to_folder(self, folder_id: str, new_parent_id):
        """Move a folder under a new parent (None = root)."""
        for f in self.bank_folders["folders"]:
            if f["id"] == folder_id:
                f["parent_id"] = new_parent_id
                break
        save_bank_folders(self.sav_path, self.bank_folders)
        self._refresh_mtime()


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
        save_tokens(self.sav_path, self.tokens)
        self._refresh_mtime()

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

    def apply_send_gift_multiple(self, indices: list[int], src_key: str = "storage") -> int:
        """Send multiple items from *src_key* inventory as gifts in one DB transaction.

        Returns count sent.  When *src_key* is ``"bank"``, the items' folder
        assignments are also cleaned up from ``bank_folders``.
        """
        from utils.gift_manager import send_gifts_batch
        ctx = self.get_gift_context()
        if not ctx["is_known_user"]:
            raise ValueError("Cannot determine gift recipient — save file user ID not recognized.")

        inventory    = self.inventories[src_key]
        raws_to_send = [inventory.raws[idx] for idx in indices]

        send_gifts_batch(raws_to_send, ctx["recipient_id"])

        for idx in sorted(indices, reverse=True):
            if src_key == "bank":
                seq_id = str(inventory.raws[idx].get("seqId", ""))
                self.bank_folders["item_folders"].pop(seq_id, None)
            del inventory.raws[idx]
            del inventory.items[idx]
            inventory.count -= 1

        self.save_inventories()
        if src_key == "bank":
            save_bank_folders(self.sav_path, self.bank_folders)
        self._refresh_mtime()
        return len(indices)

    def apply_receive_gifts(self) -> list[dict]:
        """Fetch all pending gifts, add them to the bank and pool, persist. Returns the raw items."""
        from utils.gift_manager import receive_gifts, get_steam_id_from_path
        my_id = get_steam_id_from_path(self.sav_path)
        if my_id is None:
            return []

        raw_items = receive_gifts(my_id)
        if not raw_items:
            return []

        bank         = self.inventories["bank"]
        pool_changed = False

        for raw in raw_items:
            new_seq_id = max((r.get("seqId", 0) for r in bank.raws), default=0) + 1
            new_raw    = {**raw, "seqId": new_seq_id}
            # Normalize subname key so it round-trips correctly
            if "subname" in new_raw and "subName" not in new_raw:
                new_raw["subName"] = new_raw.pop("subname")
            bank.raws.append(new_raw)
            bank.items.append(Item(new_raw))
            bank.count += 1

            # Add to pool if not already discovered (same rule as load_data)
            name = new_raw.get("name")
            if name and name not in self.items_pool and name not in POOL_NAME_BLACKLIST:
                self.items_pool[name] = new_raw
                pool_changed = True

        self.save_inventories()

        if pool_changed:
            save_items_pool(self.items_pool)
            # Rebuild in-memory pool so the UI reflects the new discoveries immediately
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
            self.inv_items["Pool"] = self.pool_items + self.undiscovered_pool_items

        return raw_items

