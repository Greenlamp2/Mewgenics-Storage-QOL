"""
Token Shop — Lootbox system.

Spending 3 identical tokens opens a Lootbox of the same rarity.
The lootbox contains ITEMS_PER_LOOTBOX items whose individual rarities
are sampled from LOOT_DISTRIBUTIONS[lootbox_rarity].
The player then picks MAX_PICKS items to add to their storage.
"""
import os
import random

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QPixmap, QPainter
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QWidget, QFrame, QMessageBox, QGridLayout,
    QGraphicsOpacityEffect,
)

from parse.item import Item
from utils.savers import save_inventories, save_tokens

ICON_DIR   = os.path.join(os.path.dirname(os.path.dirname(__file__)), "assets", "img")
TOKENS_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "assets", "icons", "tokens")

RARITIES_IN_SHOP = ("common", "uncommon", "rare", "very_rare")
TOKEN_COST        = 5
ITEMS_PER_LOOTBOX = 8
MAX_PICKS         = 2

# Per-rarity probability table for items INSIDE each lootbox tier
LOOT_DISTRIBUTIONS: dict[str, dict[str, float]] = {
    "very_rare": {"very_rare": 0.75, "rare": 0.25, "uncommon": 0.00, "common": 0.00},
    "rare":      {"very_rare": 0.01, "rare": 0.75, "uncommon": 0.24, "common": 0.00},
    "uncommon":  {"very_rare": 0.00, "rare": 0.05, "uncommon": 0.65, "common": 0.30},
    "common":    {"very_rare": 0.00, "rare": 0.00, "uncommon": 0.10, "common": 0.90},
}

# Minimum discovered items of a rarity to unlock that lootbox tier
POOL_REQUIRED = {
    "common":    20,
    "uncommon":  20,
    "rare":      20,
    "very_rare": 10,
}

# Item categories never offered inside a lootbox
LOOTBOX_CATEGORY_BLACKLIST: frozenset[str] = frozenset({
    "modifiers",
    "legendary",
})

RARITY_COLORS = {
    "common":               "#d0d0d0",
    "uncommon":             "#888888",
    "rare":                 "#c8a830",
    "very_rare":            "#c04040",
    "consumable_common":    "#d0d0d0",
    "consumable_uncommon":  "#888888",
    "consumable_rare":      "#c8a830",
    "consumable_very_rare": "#c04040",
}
RARITY_BG_SOLID = {
    "common":    "#262626",
    "uncommon":  "#222222",
    "rare":      "#2a2400",
    "very_rare": "#280808",
}
RARITY_LABEL = {
    "common":    "Common",
    "uncommon":  "Uncommon",
    "rare":      "Rare",
    "very_rare": "Very Rare",
}


def svg_to_pixmap(svg_path: str, size: int) -> QPixmap:
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    if os.path.exists(svg_path):
        renderer = QSvgRenderer(svg_path)
        painter  = QPainter(pixmap)
        renderer.render(painter)
        painter.end()
    return pixmap


# ──────────────────────────────────────────────────────────────────────
# Item card (selectable)
# ──────────────────────────────────────────────────────────────────────

class ItemCard(QFrame):
    """Clickable card showing one item; visually selected/dimmed by the dialog."""

    clicked = Signal(int)   # emits the card index

    CARD_W = 145
    CARD_H = 185

    def __init__(self, idx: int, item: Item, parent=None):
        super().__init__(parent)
        self.idx       = idx
        self.item      = item
        self._selected = False
        self._dimmed   = False
        self.setFixedSize(self.CARD_W, self.CARD_H)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._build_ui()
        self._refresh_style()

    # ------------------------------------------------------------------

    def _build_ui(self):
        vbox = QVBoxLayout(self)
        vbox.setContentsMargins(8, 10, 8, 8)
        vbox.setSpacing(4)
        vbox.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignHCenter)

        # Icon wrapper with rarity background
        icon_wrap = QWidget()
        icon_wrap.setFixedSize(70, 70)
        icon_wrap.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        rarity_raw = (self.item.details or {}).get("rarity", "common") or "common"
        bg = RARITY_BG_SOLID.get(rarity_raw.replace("consumable_", ""), "#222")
        icon_wrap.setStyleSheet(f"background: {bg}; border-radius: 8px;")
        iw = QHBoxLayout(icon_wrap)
        iw.setContentsMargins(5, 5, 5, 5)
        self.icon_lbl = QLabel()
        self.icon_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon_path = os.path.join(ICON_DIR, self.item.icon_name or "")
        self.icon_lbl.setPixmap(svg_to_pixmap(icon_path, 58))
        iw.addWidget(self.icon_lbl)
        vbox.addWidget(icon_wrap, alignment=Qt.AlignmentFlag.AlignHCenter)

        # Name
        display_name = (self.item.details or {}).get("name_resolved") or self.item.name or "?"
        name_lbl = QLabel(display_name)
        name_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        name_lbl.setWordWrap(True)
        name_lbl.setFixedHeight(38)
        name_lbl.setStyleSheet(
            "color: #eeeeee; font-size: 11px; font-weight: bold; background: transparent;"
        )
        vbox.addWidget(name_lbl)

        # Rarity badge
        rarity = self.item.rarity or "common"
        color  = RARITY_COLORS.get(rarity, "#ccc")
        rar_lbl = QLabel(RARITY_LABEL.get(rarity, rarity.capitalize()))
        rar_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        rar_lbl.setStyleSheet(
            f"color: {color}; font-size: 10px; font-weight: bold; background: transparent;"
        )
        vbox.addWidget(rar_lbl)

        vbox.addStretch()

        # Checkmark (shown when selected)
        self.check_lbl = QLabel("✓")
        self.check_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.check_lbl.setStyleSheet(
            "color: #4caf50; font-size: 20px; font-weight: bold; background: transparent;"
        )
        self.check_lbl.setVisible(False)
        vbox.addWidget(self.check_lbl)

        # Tooltip with description
        details = self.item.details or {}
        desc    = details.get("desc_resolved") or ""
        if desc:
            for key, val in details.items():
                if key not in ("name", "desc", "name_resolved", "desc_resolved", "rarity", "kind"):
                    try:
                        desc = desc.replace(f"{{{key}}}", str(val))
                    except Exception:
                        pass
        cat     = self.item.category or "—"
        tooltip = f"{display_name}\nRarity: {RARITY_LABEL.get(rarity, rarity)}\nCategory: {cat}"
        if desc:
            tooltip += f"\n\n{desc}"
        self.setToolTip(tooltip)

    # ------------------------------------------------------------------

    def set_selected(self, v: bool):
        self._selected = v
        self.check_lbl.setVisible(v)
        self._refresh_style()

    def set_dimmed(self, v: bool):
        self._dimmed = v
        self._refresh_style()
        self.setCursor(
            Qt.CursorShape.ForbiddenCursor if v
            else Qt.CursorShape.PointingHandCursor
        )

    def _refresh_style(self):
        rarity = self.item.rarity or "common"
        color  = RARITY_COLORS.get(rarity, "#ccc")

        if self._selected:
            self.setStyleSheet(
                "ItemCard { background: #0d2010; border: 3px solid #4caf50;"
                " border-radius: 10px; }"
            )
            self.setGraphicsEffect(None)
        elif self._dimmed:
            self.setStyleSheet(
                "ItemCard { background: #111; border: 2px solid #252525;"
                " border-radius: 10px; }"
            )
            eff = QGraphicsOpacityEffect(self)
            eff.setOpacity(0.35)
            self.setGraphicsEffect(eff)
        else:
            self.setStyleSheet(
                f"ItemCard {{ background: #1a1a1a;"
                f" border: 2px solid {color}55; border-radius: 10px; }}"
                f"ItemCard:hover {{ background: #222;"
                f" border: 2px solid {color}; }}"
            )
            self.setGraphicsEffect(None)

    def mousePressEvent(self, event):
        if not self._dimmed:
            self.clicked.emit(self.idx)


# ──────────────────────────────────────────────────────────────────────
# Rarity button (token spender)
# ──────────────────────────────────────────────────────────────────────

class TokenButton(QFrame):
    clicked = Signal(str)   # emits rarity

    def __init__(self, rarity: str, parent=None):
        super().__init__(parent)
        self.rarity   = rarity
        self._enabled = False
        self.setFixedSize(155, 120)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        vbox = QVBoxLayout(self)
        vbox.setAlignment(Qt.AlignmentFlag.AlignCenter)
        vbox.setSpacing(3)
        vbox.setContentsMargins(8, 8, 8, 8)

        # Token icon
        self.icon_lbl = QLabel()
        self.icon_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.icon_lbl.setFixedSize(36, 36)
        pix = QPixmap(os.path.join(TOKENS_DIR, f"{rarity}.png"))
        if not pix.isNull():
            self.icon_lbl.setPixmap(
                pix.scaled(36, 36, Qt.AspectRatioMode.KeepAspectRatio,
                           Qt.TransformationMode.SmoothTransformation)
            )
        vbox.addWidget(self.icon_lbl, alignment=Qt.AlignmentFlag.AlignHCenter)

        self.name_lbl  = QLabel(RARITY_LABEL.get(rarity, rarity.capitalize()))
        self.name_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        vbox.addWidget(self.name_lbl)

        self.count_lbl = QLabel()
        self.count_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        vbox.addWidget(self.count_lbl)

        self.req_lbl   = QLabel()
        self.req_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        vbox.addWidget(self.req_lbl)

    def update_state(self, token_count: int, pool_count: int, debug: bool = False):
        required      = POOL_REQUIRED.get(self.rarity, 20)
        has_tokens    = debug or token_count >= TOKEN_COST
        has_discovery = pool_count >= required
        self._enabled = has_tokens and has_discovery

        color  = RARITY_COLORS.get(self.rarity, "#fff")
        bg     = RARITY_BG_SOLID.get(self.rarity, "#222")
        border = color if self._enabled else "#444"

        self.setStyleSheet(
            f"TokenButton {{ background: {bg}; border: 2px solid {border}; border-radius: 8px; }}"
            f"TokenButton:hover {{ border: 3px solid {border}; }}"
        )
        self.name_lbl.setStyleSheet(
            f"font-size: 13px; font-weight: bold;"
            f" color: {color if self._enabled else '#555'};"
        )

        if debug:
            self.count_lbl.setStyleSheet("font-size: 11px; color: #4caf50;")
            self.count_lbl.setText("∞ tokens")
        else:
            tc = "#ffffff" if has_tokens else "#e53935"
            self.count_lbl.setStyleSheet(f"font-size: 11px; color: {tc};")
            self.count_lbl.setText(f"{token_count} token{'s' if token_count != 1 else ''}")

        if has_discovery:
            self.req_lbl.setStyleSheet("font-size: 10px; color: #4caf50;")
            self.req_lbl.setText(f"✔ {pool_count} discovered")
        else:
            self.req_lbl.setStyleSheet("font-size: 10px; color: #888;")
            self.req_lbl.setText(f"{pool_count} / {required} needed")

        if not has_discovery:
            self.setToolTip(
                f"Discover {required - pool_count} more {RARITY_LABEL.get(self.rarity)} items"
            )
        elif not has_tokens:
            self.setToolTip(f"Need {TOKEN_COST} tokens (you have {token_count})")
        else:
            self.setToolTip(
                f"Spend {TOKEN_COST} {RARITY_LABEL.get(self.rarity)} tokens"
                f" to open a {RARITY_LABEL.get(self.rarity)} Lootbox"
            )
        self.setCursor(
            Qt.CursorShape.PointingHandCursor if self._enabled
            else Qt.CursorShape.ForbiddenCursor
        )

    def mousePressEvent(self, event):
        if self._enabled:
            self.clicked.emit(self.rarity)


# ──────────────────────────────────────────────────────────────────────
# Lootbox dialog
# ──────────────────────────────────────────────────────────────────────

class LootboxDialog(QDialog):
    """Shows ITEMS_PER_LOOTBOX items sampled from the pool; player picks MAX_PICKS."""

    def __init__(self, parent, rarity: str, pool_items: list, items_pool: dict,
                 sav_path: str, inventories: dict,
                 loaded_mtime: float | None = None):
        super().__init__(parent)
        self.setWindowTitle(f"Lootbox — {RARITY_LABEL.get(rarity, rarity)}")
        self.setMinimumWidth(700)
        self.setWindowModality(Qt.WindowModality.ApplicationModal)

        self.lootbox_rarity = rarity
        self.pool_items     = pool_items
        self.items_pool     = items_pool
        self.sav_path       = sav_path
        self.inventories    = inventories
        self.loaded_mtime   = loaded_mtime

        self.loot_items: list[Item]     = self._generate_items()
        self.selected_indices: set[int] = set()
        self.cards: list[ItemCard]      = []

        self._build_ui()

    # ------------------------------------------------------------------
    # Item generation
    # ------------------------------------------------------------------

    def _generate_items(self) -> list[Item]:
        dist     = LOOT_DISTRIBUTIONS.get(self.lootbox_rarity, {"common": 1.0})
        rarities = [r for r, w in dist.items() if w > 0]
        weights  = [dist[r] for r in rarities]

        # Exclude blacklisted categories upfront
        eligible = [
            i for i in self.pool_items
            if getattr(i, "category", None) not in LOOTBOX_CATEGORY_BLACKLIST
        ]

        # Pre-group eligible items by rarity for fast lookup
        by_rarity: dict[str, list[Item]] = {
            r: [i for i in eligible if getattr(i, "rarity", None) == r]
            for r in RARITIES_IN_SHOP
        }

        result: list[Item] = []
        seen:   set[str]   = set()
        attempts            = 0

        while len(result) < ITEMS_PER_LOOTBOX and attempts < 600:
            attempts += 1
            rolled   = random.choices(rarities, weights=weights, k=1)[0]
            pool     = [i for i in by_rarity.get(rolled, []) if i.name not in seen]

            if not pool:
                # Cascade fallback: try adjacent rarities then everything
                for fallback in (self.lootbox_rarity, "rare", "uncommon", "common", "very_rare"):
                    pool = [i for i in by_rarity.get(fallback, []) if i.name not in seen]
                    if pool:
                        break
            if not pool:
                pool = [i for i in eligible if i.name not in seen]

            if pool:
                item = random.choice(pool)
                result.append(item)
                seen.add(item.name)

        return result

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------

    def _build_ui(self):
        vbox = QVBoxLayout(self)
        vbox.setSpacing(12)
        vbox.setContentsMargins(20, 16, 20, 16)

        # Title
        rarity = self.lootbox_rarity
        color  = RARITY_COLORS.get(rarity, "#ccc")
        title  = QLabel(f"🎁  Lootbox {RARITY_LABEL.get(rarity, rarity)}")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet(f"font-size: 22px; font-weight: bold; color: {color};")
        vbox.addWidget(title)

        # Distribution legend
        dist  = LOOT_DISTRIBUTIONS.get(rarity, {})
        parts = [
            f'<span style="color:{RARITY_COLORS.get(r, "#ccc")}">'
            f'{RARITY_LABEL.get(r, r)} {int(w * 100)}%</span>'
            for r, w in dist.items() if w > 0
        ]
        legend = QLabel("  ·  ".join(parts))
        legend.setAlignment(Qt.AlignmentFlag.AlignCenter)
        legend.setTextFormat(Qt.TextFormat.RichText)
        legend.setStyleSheet("font-size: 11px; color: #888;")
        vbox.addWidget(legend)

        # Counter / instructions
        self.counter_lbl = QLabel(
            f"Choisissez {MAX_PICKS} objets  —  0 / {MAX_PICKS} sélectionné(s)"
        )
        self.counter_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.counter_lbl.setStyleSheet("color: #aaa; font-size: 13px; font-weight: bold;")
        vbox.addWidget(self.counter_lbl)

        # Items grid  (4 columns × 2 rows)
        grid_w = QWidget()
        grid   = QGridLayout(grid_w)
        grid.setSpacing(10)
        grid.setContentsMargins(0, 0, 0, 0)

        for i, item in enumerate(self.loot_items):
            card = ItemCard(i, item, grid_w)
            card.clicked.connect(self._on_card_click)
            self.cards.append(card)
            grid.addWidget(card, i // 4, i % 4)

        vbox.addWidget(grid_w, alignment=Qt.AlignmentFlag.AlignHCenter)

        # Selection summary
        self.summary_lbl = QLabel()
        self.summary_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.summary_lbl.setTextFormat(Qt.TextFormat.RichText)
        self.summary_lbl.setStyleSheet("color: #4caf50; font-size: 12px;")
        vbox.addWidget(self.summary_lbl)

        # Confirm button
        self.confirm_btn = QPushButton(f"➕  Ajouter {MAX_PICKS} objets au Storage")
        self.confirm_btn.setEnabled(False)
        self.confirm_btn.setStyleSheet(
            "QPushButton { font-size: 14px; font-weight: bold; padding: 10px 24px;"
            " background: #2e7d32; color: white; border: none; border-radius: 6px; }"
            "QPushButton:hover { background: #1b5e20; }"
            "QPushButton:disabled { background: #2a2a2a; color: #555; border-radius: 6px; }"
        )
        self.confirm_btn.clicked.connect(self._confirm)
        vbox.addWidget(self.confirm_btn)

    # ------------------------------------------------------------------
    # Selection logic
    # ------------------------------------------------------------------

    def _on_card_click(self, idx: int):
        if idx in self.selected_indices:
            self.selected_indices.discard(idx)
            self.cards[idx].set_selected(False)
        elif len(self.selected_indices) < MAX_PICKS:
            self.selected_indices.add(idx)
            self.cards[idx].set_selected(True)

        full = len(self.selected_indices) >= MAX_PICKS
        for i, card in enumerate(self.cards):
            if i not in self.selected_indices:
                card.set_dimmed(full)

        n     = len(self.selected_indices)
        color = "#4caf50" if n == MAX_PICKS else "#aaa"
        self.counter_lbl.setText(
            f"Choisissez {MAX_PICKS} objets  —  {n} / {MAX_PICKS} sélectionné(s)"
        )
        self.counter_lbl.setStyleSheet(f"color: {color}; font-size: 13px; font-weight: bold;")

        if self.selected_indices:
            names = [
                (self.loot_items[i].details or {}).get("name_resolved")
                or self.loot_items[i].name or "?"
                for i in sorted(self.selected_indices)
            ]
            self.summary_lbl.setText(
                "Sélectionnés : " + "  •  ".join(f"<b>{n}</b>" for n in names)
            )
        else:
            self.summary_lbl.clear()

        self.confirm_btn.setEnabled(n == MAX_PICKS)

    # ------------------------------------------------------------------
    # Confirm
    # ------------------------------------------------------------------

    def _confirm(self):
        if len(self.selected_indices) != MAX_PICKS:
            return

        # Mtime guard
        try:
            current_mtime = os.path.getmtime(self.sav_path)
        except OSError:
            current_mtime = self.loaded_mtime

        if self.loaded_mtime is not None and current_mtime > self.loaded_mtime:
            import datetime as _dt
            date_str = _dt.datetime.fromtimestamp(current_mtime).strftime("%Y-%m-%d  %H:%M:%S")
            reply = QMessageBox.warning(
                self, "⚠ Sauvegarde plus récente détectée",
                f"La sauvegarde a été modifiée depuis le chargement.\n\n"
                f"Date du fichier : {date_str}\n\n"
                f"Continuer va écraser cette version plus récente.",
                QMessageBox.StandardButton.Ok | QMessageBox.StandardButton.Cancel,
                QMessageBox.StandardButton.Cancel,
            )
            if reply != QMessageBox.StandardButton.Ok:
                return

        storage = self.inventories["storage"]
        for idx in sorted(self.selected_indices):
            item       = self.loot_items[idx]
            new_seq_id = max((r.get("seqId", 0) for r in storage.raws), default=0) + 1
            raw        = self.items_pool.get(item.name, {})
            new_raw    = {**raw, "seqId": new_seq_id}
            storage.raws.append(new_raw)
            storage.items.append(Item(new_raw))
            storage.count += 1

        save_inventories(self.sav_path, self.inventories)
        self.accept()


# ──────────────────────────────────────────────────────────────────────
# Main token shop dialog
# ──────────────────────────────────────────────────────────────────────

class TokenShopDialog(QDialog):
    def __init__(self, parent, tokens: dict, pool_items: list, items_pool: dict,
                 sav_path: str, inventories: dict,
                 loaded_mtime: float | None = None, debug: bool = False):
        super().__init__(parent)
        self.setWindowTitle("Token Shop")
        self.setMinimumWidth(740)
        self.setWindowModality(Qt.WindowModality.ApplicationModal)

        self.tokens       = dict(tokens)
        self.pool_items   = pool_items
        self.items_pool   = items_pool
        self.sav_path     = sav_path
        self.inventories  = inventories
        self.loaded_mtime = loaded_mtime
        self.debug        = debug

        self._build_ui()
        self._update_buttons()

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------

    def _build_ui(self):
        vbox = QVBoxLayout(self)
        vbox.setSpacing(16)
        vbox.setContentsMargins(24, 20, 24, 20)

        # Title + subtitle
        title = QLabel("Token Shop")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet("font-size: 24px; font-weight: bold;")
        vbox.addWidget(title)

        subtitle = QLabel(
            f"Dépensez {TOKEN_COST} tokens identiques pour ouvrir une Lootbox.\n"
            f"Choisissez ensuite {MAX_PICKS} objets parmi {ITEMS_PER_LOOTBOX} proposés."
        )
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        subtitle.setStyleSheet("color: #666; font-size: 12px;")
        subtitle.setWordWrap(True)
        vbox.addWidget(subtitle)

        # Rarity buttons
        btn_row = QWidget()
        bl      = QHBoxLayout(btn_row)
        bl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        bl.setSpacing(16)
        self.token_btns: dict[str, TokenButton] = {}
        for rarity in RARITIES_IN_SHOP:
            btn = TokenButton(rarity, btn_row)
            btn.clicked.connect(self._on_rarity_clicked)
            self.token_btns[rarity] = btn
            bl.addWidget(btn)
        vbox.addWidget(btn_row)

        # Distribution table
        table = QFrame()
        table.setStyleSheet(
            "QFrame { background: #181818; border: 1px solid #2a2a2a; border-radius: 8px; }"
        )
        tl = QVBoxLayout(table)
        tl.setContentsMargins(16, 12, 16, 12)
        tl.setSpacing(5)

        hdr = QLabel("Distribution des raretés par tier de Lootbox")
        hdr.setStyleSheet("color: #666; font-size: 11px; font-weight: bold;")
        tl.addWidget(hdr)

        for lb_rarity in RARITIES_IN_SHOP:
            row_w = QWidget()
            row_h = QHBoxLayout(row_w)
            row_h.setContentsMargins(0, 0, 0, 0)
            row_h.setSpacing(0)

            lb_color = RARITY_COLORS.get(lb_rarity, "#ccc")
            lb_lbl   = QLabel(f"🎁 {RARITY_LABEL[lb_rarity]}")
            lb_lbl.setFixedWidth(120)
            lb_lbl.setStyleSheet(f"color: {lb_color}; font-size: 11px; font-weight: bold;")
            row_h.addWidget(lb_lbl)

            dist = LOOT_DISTRIBUTIONS[lb_rarity]
            for item_rarity in RARITIES_IN_SHOP:
                w = dist.get(item_rarity, 0)
                if w > 0:
                    ic   = RARITY_COLORS.get(item_rarity, "#ccc")
                    cell = QLabel(
                        f'<span style="color:{ic}">'
                        f'{RARITY_LABEL[item_rarity]} {int(w * 100)}%</span>'
                    )
                    cell.setTextFormat(Qt.TextFormat.RichText)
                    cell.setFixedWidth(115)
                    cell.setStyleSheet("font-size: 11px;")
                    row_h.addWidget(cell)

            row_h.addStretch()
            tl.addWidget(row_w)

        vbox.addWidget(table)
        vbox.addStretch()

    # ------------------------------------------------------------------

    def _pool_count(self, rarity: str) -> int:
        return sum(1 for it in self.pool_items if getattr(it, "rarity", None) == rarity)

    def _update_buttons(self):
        for rarity, btn in self.token_btns.items():
            btn.update_state(
                token_count=self.tokens.get(rarity, 0),
                pool_count=self._pool_count(rarity),
                debug=self.debug,
            )

    # ------------------------------------------------------------------

    def _on_rarity_clicked(self, rarity: str):
        if not self.debug and self.tokens.get(rarity, 0) < TOKEN_COST:
            return

        label = RARITY_LABEL.get(rarity, rarity.capitalize())
        reply = QMessageBox.question(
            self,
            "Ouvrir une Lootbox",
            f"Dépenser {TOKEN_COST} tokens {label} pour ouvrir une Lootbox {label} ?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        if not self.debug:
            self.tokens[rarity] -= TOKEN_COST
            mtime = self.loaded_mtime or (
                os.path.getmtime(self.sav_path) if os.path.exists(self.sav_path) else 0.0
            )
            save_tokens(self.tokens, mtime)

        self._update_buttons()

        dlg = LootboxDialog(
            parent=self,
            rarity=rarity,
            pool_items=self.pool_items,
            items_pool=self.items_pool,
            sav_path=self.sav_path,
            inventories=self.inventories,
            loaded_mtime=self.loaded_mtime,
        )
        dlg.exec()

