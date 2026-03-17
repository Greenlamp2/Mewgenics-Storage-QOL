import os
import random

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QPixmap, QPainter
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QWidget, QFrame, QMessageBox,
)

from parse.item import Item
from utils.savers import save_inventories, save_tokens

ICON_DIR   = os.path.join(os.path.dirname(os.path.dirname(__file__)), "assets", "img")
TOKENS_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "assets", "icons", "tokens")

RARITIES_IN_SHOP = ("common", "uncommon", "rare", "very_rare")
RARITY_UPGRADE   = {"common": "uncommon", "uncommon": "rare", "rare": None, "very_rare": None}
UPGRADE_CHANCE   = 0.01
MAX_REROLLS      = 3
POOL_REQUIRED = {
    "common":    20,
    "uncommon":  20,
    "rare":      20,
    "very_rare": 10,
}

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
RARITY_BG = {
    "common":               "#262626",
    "uncommon":             "#222222",
    "rare":                 "#262400",
    "very_rare":            "#260808",
    "consumable_common":    "#262626",
    "consumable_uncommon":  "#222222",
    "consumable_rare":      "#262400",
    "consumable_very_rare": "#260808",
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
        painter = QPainter(pixmap)
        renderer.render(painter)
        painter.end()
    return pixmap


# ──────────────────────────────────────────────────────────────────────
# Custom token button widget
# ──────────────────────────────────────────────────────────────────────

class TokenButton(QFrame):
    clicked = Signal(str)   # rarity

    def __init__(self, rarity: str, parent=None):
        super().__init__(parent)
        self.rarity = rarity
        self._enabled = False
        self.setFixedSize(150, 130)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.setSpacing(4)
        layout.setContentsMargins(8, 10, 8, 10)

        self.icon_lbl = QLabel()
        self.icon_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.icon_lbl.setFixedSize(40, 40)
        layout.addWidget(self.icon_lbl, alignment=Qt.AlignmentFlag.AlignCenter)

        self.name_lbl = QLabel(RARITY_LABEL.get(rarity, rarity.capitalize()))
        self.name_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.name_lbl)

        self.tokens_lbl = QLabel()
        self.tokens_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.tokens_lbl)

        self.discovery_lbl = QLabel()
        self.discovery_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.discovery_lbl)

        # Load icon once
        icon_path = os.path.join(TOKENS_DIR, f"{rarity}.png")
        pixmap = QPixmap(icon_path)
        if not pixmap.isNull():
            self.icon_lbl.setPixmap(pixmap.scaled(
                40, 40,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            ))

    def update_state(self, token_count: int, pool_count: int):
        required      = POOL_REQUIRED.get(self.rarity, 20)
        has_tokens    = token_count >= 3
        has_discovery = pool_count >= required
        self._enabled = has_tokens and has_discovery

        color = RARITY_COLORS.get(self.rarity, "#fff")
        bg    = RARITY_BG.get(self.rarity, "#222")
        border_color = color if self._enabled else "#444"

        self.setStyleSheet(
            f"TokenButton {{"
            f"  background: {bg};"
            f"  border: 2px solid {border_color};"
            f"  border-radius: 8px;"
            f"}}"
            f"TokenButton:hover {{"
            f"  border: 3px solid {border_color};"
            f"}}"
        )

        self.name_lbl.setStyleSheet(
            f"font-size: 13px; font-weight: bold;"
            f" color: {color if self._enabled else '#666'};"
        )

        token_color = "#fff" if has_tokens else "#e53935"
        self.tokens_lbl.setStyleSheet(f"font-size: 11px; color: {token_color};")
        self.tokens_lbl.setText(f"{token_count} token{'s' if token_count != 1 else ''}")

        if has_discovery:
            disc_color = "#4caf50"
            disc_text  = f"✔ {pool_count} discovered"
        else:
            disc_color = "#888"
            disc_text  = f"{pool_count} / {required} discovered"
        self.discovery_lbl.setStyleSheet(f"font-size: 10px; color: {disc_color};")
        self.discovery_lbl.setText(disc_text)

        # Tooltip
        if not has_discovery:
            self.setToolTip(f"Discover {required - pool_count} more {RARITY_LABEL.get(self.rarity)} items")
        elif not has_tokens:
            self.setToolTip(f"Need 3 tokens (you have {token_count})")
        else:
            self.setToolTip(f"Spend 3 {RARITY_LABEL.get(self.rarity)} tokens")

        self.setCursor(
            Qt.CursorShape.PointingHandCursor if self._enabled
            else Qt.CursorShape.ForbiddenCursor
        )

    def mousePressEvent(self, event):
        if self._enabled:
            self.clicked.emit(self.rarity)


# ──────────────────────────────────────────────────────────────────────
# Dialog
# ──────────────────────────────────────────────────────────────────────

class TokenShopDialog(QDialog):
    def __init__(self, parent, tokens: dict, pool_items: list, items_pool: dict,
                 sav_path: str, inventories: dict, loaded_mtime: float | None = None):
        super().__init__(parent)
        self.setWindowTitle("Token Shop")
        self.setMinimumWidth(520)
        self.setMinimumHeight(500)
        self.setWindowModality(Qt.WindowModality.ApplicationModal)

        self.tokens      = dict(tokens)
        self.pool_items  = pool_items
        self.items_pool  = items_pool
        self.sav_path    = sav_path
        self.inventories = inventories
        self.loaded_mtime = loaded_mtime

        self.current_item: Item | None = None
        self.current_rarity: str | None = None
        self.rerolls_left: int = 0

        self._build_ui()
        self._update_token_buttons()

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(14)
        layout.setContentsMargins(20, 16, 20, 16)

        title = QLabel("Token Shop")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet("font-size: 22px; font-weight: bold;")
        layout.addWidget(title)

        subtitle = QLabel("Spend 3 tokens · 1 % chance to receive the rarity above")
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        subtitle.setStyleSheet("color: #777; font-size: 12px;")
        layout.addWidget(subtitle)

        # Token buttons
        token_row = QWidget()
        token_layout = QHBoxLayout(token_row)
        token_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        token_layout.setSpacing(12)
        self.token_btns: dict[str, TokenButton] = {}
        for rarity in RARITIES_IN_SHOP:
            btn = TokenButton(rarity, self)
            btn.clicked.connect(self._spend_tokens)
            self.token_btns[rarity] = btn
            token_layout.addWidget(btn)
        layout.addWidget(token_row)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        layout.addWidget(sep)

        # Item preview
        self.item_icon = QLabel()
        self.item_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.item_icon.setFixedSize(64, 64)
        icon_wrapper = QWidget()
        iw = QHBoxLayout(icon_wrapper)
        iw.addStretch()
        iw.addWidget(self.item_icon)
        iw.addStretch()
        layout.addWidget(icon_wrapper)

        self.item_name = QLabel("—")
        self.item_name.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.item_name.setStyleSheet("font-size: 15px; font-weight: bold;")
        self.item_name.setWordWrap(True)
        layout.addWidget(self.item_name)

        self.item_info = QLabel()
        self.item_info.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.item_info.setWordWrap(True)
        self.item_info.setTextFormat(Qt.TextFormat.RichText)
        layout.addWidget(self.item_info)

        layout.addStretch()

        # Action buttons
        action_row = QWidget()
        action_layout = QHBoxLayout(action_row)
        action_layout.setSpacing(8)

        self.reroll_btn = QPushButton()
        self.reroll_btn.setVisible(False)
        self.reroll_btn.setStyleSheet(
            "QPushButton { font-size: 13px; font-weight: bold; padding: 6px 14px;"
            " background: #e65100; color: white; border: none; border-radius: 4px; }"
            "QPushButton:hover { background: #bf360c; }"
            "QPushButton:disabled { background: #3a3a3a; color: #666; }"
        )
        self.reroll_btn.clicked.connect(self._reroll)
        action_layout.addWidget(self.reroll_btn)

        self.take_btn = QPushButton("➕ Add to Storage")
        self.take_btn.setVisible(False)
        self.take_btn.setStyleSheet(
            "QPushButton { font-size: 13px; font-weight: bold; padding: 6px 14px;"
            " background: #2e7d32; color: white; border: none; border-radius: 4px; }"
            "QPushButton:hover { background: #1b5e20; }"
        )
        self.take_btn.clicked.connect(self._take_item)
        action_layout.addWidget(self.take_btn)

        layout.addWidget(action_row)

    # ------------------------------------------------------------------
    # Token buttons
    # ------------------------------------------------------------------

    def _pool_count(self, rarity: str) -> int:
        return sum(
            1 for item in self.pool_items
            if getattr(item, "rarity", None) == rarity
        )

    def _update_token_buttons(self):
        for rarity, btn in self.token_btns.items():
            btn.update_state(
                token_count=self.tokens.get(rarity, 0),
                pool_count=self._pool_count(rarity),
            )

    # ------------------------------------------------------------------
    # Spend tokens
    # ------------------------------------------------------------------

    def _spend_tokens(self, rarity: str):
        if self.tokens.get(rarity, 0) < 3:
            return

        label = RARITY_LABEL.get(rarity, rarity.capitalize())
        reply = QMessageBox.question(
            self,
            "Confirmation",
            f"Spend 3 {label} tokens?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        self.tokens[rarity] -= 3
        self.current_rarity  = rarity
        self.rerolls_left    = MAX_REROLLS

        effective_rarity = rarity
        upgrade = RARITY_UPGRADE.get(rarity)
        if upgrade and random.random() < UPGRADE_CHANCE:
            effective_rarity = upgrade

        self._pick_item(effective_rarity, fallback=rarity)
        self._update_token_buttons()
        mtime = self.loaded_mtime if self.loaded_mtime is not None else (
            os.path.getmtime(self.sav_path) if os.path.exists(self.sav_path) else 0.0
        )
        save_tokens(self.tokens, mtime)

    # ------------------------------------------------------------------
    # Item picking
    # ------------------------------------------------------------------

    def _candidates(self, rarity: str) -> list[Item]:
        return [
            item for item in self.pool_items
            if getattr(item, "rarity", None) == rarity
        ]

    def _pick_item(self, rarity: str, fallback: str | None = None):
        candidates = self._candidates(rarity)
        if not candidates and fallback and fallback != rarity:
            candidates = self._candidates(fallback)
        if not candidates:
            self.current_item = None
            self.item_name.setText("No items available for this rarity")
            self.item_info.clear()
            self.item_icon.clear()
            self.reroll_btn.setVisible(False)
            self.take_btn.setVisible(False)
            return
        self.current_item = random.choice(candidates)
        self._display_item()
        self._refresh_action_btns()

    def _display_item(self):
        item    = self.current_item
        details = item.details or {}
        icon_path = os.path.join(ICON_DIR, item.icon_name or "")
        self.item_icon.setPixmap(svg_to_pixmap(icon_path, 64))
        name = details.get("name_resolved") or item.name or "?"
        self.item_name.setText(name)
        lines = []
        rarity = details.get("rarity")
        if rarity:
            color = RARITY_COLORS.get(rarity, "#ccc")
            lines.append(
                f'<b>Rarity:</b> <span style="color:{color}">'
                f'{RARITY_LABEL.get(rarity, rarity.capitalize())}</span>'
            )
        cat = item.category or "—"
        lines.append(f"<b>Category:</b> {cat}")
        desc = details.get("desc_resolved")
        if desc:
            lines.append(f"<br><i>{desc}</i>")
        self.item_info.setText("<br>".join(lines))

    def _refresh_action_btns(self):
        self.reroll_btn.setText(f"🎲 Reroll ({self.rerolls_left} left)")
        self.reroll_btn.setEnabled(self.rerolls_left > 0)
        self.reroll_btn.setVisible(True)
        self.take_btn.setVisible(True)

    # ------------------------------------------------------------------
    # Reroll
    # ------------------------------------------------------------------

    def _reroll(self):
        if self.rerolls_left <= 0 or not self.current_item:
            return
        self.rerolls_left -= 1
        rarity = (self.current_item.details or {}).get("rarity") or self.current_rarity
        self._pick_item(rarity)

    # ------------------------------------------------------------------
    # Take item
    # ------------------------------------------------------------------

    def _take_item(self):
        if not self.current_item:
            return

        # Warn if the save file changed since we opened the shop
        try:
            current_mtime = os.path.getmtime(self.sav_path)
        except OSError:
            current_mtime = self.loaded_mtime

        if self.loaded_mtime is not None and current_mtime > self.loaded_mtime:
            import datetime as _dt
            date_str = _dt.datetime.fromtimestamp(current_mtime).strftime("%Y-%m-%d  %H:%M:%S")
            reply = QMessageBox.warning(
                self,
                "⚠ Sauvegarde plus récente détectée",
                f"La sauvegarde a été modifiée depuis le chargement.\n\n"
                f"Date du fichier : {date_str}\n\n"
                f"Continuer va écraser cette version plus récente.\n"
                f"Il est recommandé de fermer et faire un Reload d'abord.",
                QMessageBox.StandardButton.Ok | QMessageBox.StandardButton.Cancel,
                QMessageBox.StandardButton.Cancel,
            )
            if reply != QMessageBox.StandardButton.Ok:
                return

        storage    = self.inventories["storage"]
        new_seq_id = max((r.get("seqId", 0) for r in storage.raws), default=0) + 1
        raw        = self.items_pool.get(self.current_item.name, {})
        new_raw    = {**raw, "seqId": new_seq_id}
        storage.raws.append(new_raw)
        storage.items.append(Item(new_raw))
        storage.count += 1
        save_inventories(self.sav_path, self.inventories)
        self.accept()

