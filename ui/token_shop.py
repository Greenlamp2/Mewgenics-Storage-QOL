import os
import random

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QPixmap, QPainter
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QWidget, QFrame, QMessageBox, QScrollArea, QGraphicsOpacityEffect,
)

from parse.item import Item
from utils.savers import save_inventories, save_tokens

ICON_DIR   = os.path.join(os.path.dirname(os.path.dirname(__file__)), "assets", "img")
TOKENS_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "assets", "icons", "tokens")

RARITIES_IN_SHOP = ("common", "uncommon", "rare", "very_rare")
RARITY_UPGRADE   = {"common": "uncommon", "uncommon": "rare", "rare": None, "very_rare": None}
UPGRADE_CHANCE   = 0.03
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


# Module-level references kept alive so the player isn't GC'd mid-playback
_fx_player = None
_fx_output = None


def play_victory_fx() -> None:
    """Play fx/victory.mp3 when an upgrade rarity is rolled."""
    global _fx_player, _fx_output
    try:
        from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput
        from PySide6.QtCore import QUrl
        from utils.paths import resource_path

        fx_path = resource_path("fx/victory.mp3")
        if not os.path.exists(fx_path):
            return

        if _fx_player is None:
            _fx_player = QMediaPlayer()
            _fx_output = QAudioOutput()
            _fx_player.setAudioOutput(_fx_output)
            _fx_player.setSource(QUrl.fromLocalFile(os.path.abspath(fx_path)))

        _fx_player.stop()
        _fx_player.play()
    except Exception:
        pass  # never crash if audio is unavailable


# ──────────────────────────────────────────────────────────────────────
# Reusable loot-preview panel (shared by main dialog & reroll dialog)
# ──────────────────────────────────────────────────────────────────────

class LootPreviewPanel(QWidget):
    """Scrollable list of pool items with probabilities for a given rarity."""

    item_clicked = Signal(object)   # emits the Item when clicked in debug mode

    def __init__(self, pool_items: list, debug: bool = False, parent=None):
        super().__init__(parent)
        self.pool_items = pool_items
        self._debug = debug
        self.current_rarity: str | None = None
        self.seen_names: set = set()
        self._build_ui()

    def _build_ui(self):
        vbox = QVBoxLayout(self)
        vbox.setContentsMargins(0, 0, 0, 0)
        vbox.setSpacing(4)

        self.title_lbl = QLabel("🎲 Survolez une rareté pour voir les loots possibles")
        self.title_lbl.setStyleSheet("color: #555; font-size: 11px; font-style: italic;")
        vbox.addWidget(self.title_lbl)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")

        self._content = QWidget()
        self._content.setStyleSheet("background: transparent;")
        self._vbox = QVBoxLayout(self._content)
        self._vbox.setContentsMargins(0, 0, 4, 0)
        self._vbox.setSpacing(1)
        self._vbox.addStretch()
        self.scroll.setWidget(self._content)
        vbox.addWidget(self.scroll)

    # public API --------------------------------------------------------

    def show_rarity(self, rarity: str, seen_names: set | None = None):
        self.current_rarity = rarity
        if seen_names is not None:
            self.seen_names = set(seen_names)
        self._rebuild()

    def update_seen(self, seen_names: set):
        self.seen_names = set(seen_names)
        if self.current_rarity:
            self._rebuild()

    # internals ---------------------------------------------------------

    def _compute_loot_probs(self, rarity: str, seen_names: set | None = None) -> list[tuple]:
        """Return (item, probability, effective_rarity) for every item.
        Probabilities are computed from the *unseen* pool so they reflect
        the actual odds for the next pick after each reroll."""
        sn = seen_names or set()
        base_items    = [i for i in self.pool_items if getattr(i, "rarity", None) == rarity]
        upgrade_rarity = RARITY_UPGRADE.get(rarity)
        upgrade_items = (
            [i for i in self.pool_items if getattr(i, "rarity", None) == upgrade_rarity]
            if upgrade_rarity else []
        )

        avail_base    = [i for i in base_items    if i.name not in sn]
        avail_upgrade = [i for i in upgrade_items if i.name not in sn]
        n_avail_base    = len(avail_base)
        n_avail_upgrade = len(avail_upgrade)

        def name_key(it):
            return ((it.details or {}).get("name_resolved") or it.name or "").lower()

        if upgrade_items:
            if n_avail_upgrade > 0:
                p_base    = (1.0 - UPGRADE_CHANCE) / n_avail_base if n_avail_base else 0.0
                p_upgrade = UPGRADE_CHANCE / n_avail_upgrade
            else:
                # All upgrade items already seen → full chance on base pool
                p_base    = 1.0 / n_avail_base if n_avail_base else 0.0
                p_upgrade = 0.0
        else:
            p_base    = 1.0 / n_avail_base if n_avail_base else 0.0
            p_upgrade = 0.0

        result  = [(it, p_base    if it.name not in sn else 0.0, rarity)
                   for it in sorted(base_items,    key=name_key)]
        result += [(it, p_upgrade if it.name not in sn else 0.0, upgrade_rarity)
                   for it in sorted(upgrade_items, key=name_key)]
        return result

    def _make_row(self, item, prob: float, rarity: str, is_seen: bool) -> QWidget:
        color = RARITY_COLORS.get(rarity, "#ccc") if not is_seen else "#3a3a3a"
        row = QWidget()

        # Debug: clickable rows for unseen items
        if self._debug and not is_seen:
            row.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
            row.setStyleSheet(
                "QWidget { background: transparent; border-radius: 3px; }"
                "QWidget:hover { background: rgba(74,158,255,0.12);"
                " border: 1px solid rgba(74,158,255,0.35); }"
            )
            row.setCursor(Qt.CursorShape.PointingHandCursor)
            row.mousePressEvent = lambda e, it=item: self.item_clicked.emit(it)
        else:
            row.setStyleSheet("background: transparent;")

        hl = QHBoxLayout(row)
        hl.setContentsMargins(2, 1, 4, 1)
        hl.setSpacing(6)

        dot = QLabel("✓" if is_seen else "●")
        dot.setFixedWidth(10)
        dot.setStyleSheet(f"color: {color}; font-size: 8px;")
        hl.addWidget(dot)

        icon_lbl = QLabel()
        icon_lbl.setFixedSize(18, 18)
        pix = svg_to_pixmap(os.path.join(ICON_DIR, item.icon_name or ""), 18)
        if is_seen:
            eff = QGraphicsOpacityEffect()
            eff.setOpacity(0.25)
            icon_lbl.setGraphicsEffect(eff)
        icon_lbl.setPixmap(pix)
        hl.addWidget(icon_lbl)

        display_name = (item.details or {}).get("name_resolved") or item.name or "?"
        name_lbl = QLabel(display_name)
        name_lbl.setStyleSheet(
            "color: #3a3a3a; font-size: 11px; text-decoration: line-through;"
            if is_seen else "color: #cccccc; font-size: 11px;"
        )
        hl.addWidget(name_lbl, stretch=1)

        prob_lbl = QLabel("—" if is_seen else f"{prob * 100:.2f} %")
        prob_lbl.setFixedWidth(58)
        prob_lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        prob_lbl.setStyleSheet(
            f"color: {color}; font-size: 11px;"
            + (" font-weight: bold;" if not is_seen else "")
        )
        hl.addWidget(prob_lbl)

        if self._debug and not is_seen:
            row.setToolTip(f"[DEBUG] Cliquer pour forcer → {display_name}")
        else:
            row.setToolTip(
                f"{display_name}  —  Déjà proposé"
                if is_seen else
                f"{display_name}  —  {prob * 100:.2f} % de chance"
            )
        return row

    def _rebuild(self):
        rarity = self.current_rarity
        if not rarity:
            return

        while self._vbox.count() > 1:
            child = self._vbox.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

        probs       = self._compute_loot_probs(rarity, self.seen_names)
        base_all    = [(it, p) for it, p, r in probs if r == rarity]
        upgrade_all = [(it, p, r) for it, p, r in probs if r != rarity]

        base_unseen = [(it, p) for it, p in base_all if it.name not in self.seen_names]
        base_seen   = [(it, p) for it, p in base_all if it.name in     self.seen_names]

        upgrade_rarity = RARITY_UPGRADE.get(rarity)
        color          = RARITY_COLORS.get(rarity, "#ccc")
        n_avail        = len(base_unseen)
        n_total        = len(base_all)

        if upgrade_all:
            title_text = (
                f"🎲 {RARITY_LABEL.get(rarity)} — {n_avail}/{n_total} restants"
                f"  ({int((1-UPGRADE_CHANCE)*100)}% base"
                f" · {int(UPGRADE_CHANCE*100)}% → {RARITY_LABEL.get(upgrade_rarity)})"
            )
        else:
            title_text = f"🎲 {RARITY_LABEL.get(rarity)} — {n_avail}/{n_total} disponibles"

        self.title_lbl.setStyleSheet(f"color: {color}; font-size: 11px; font-weight: bold;")
        self.title_lbl.setText(title_text)

        pos = 0
        for it, p in base_unseen:
            self._vbox.insertWidget(pos, self._make_row(it, p, rarity, False)); pos += 1
        for it, p in base_seen:
            self._vbox.insertWidget(pos, self._make_row(it, p, rarity, True));  pos += 1

        if upgrade_all:
            up_unseen = [(it, p, r) for it, p, r in upgrade_all if it.name not in self.seen_names]
            up_seen   = [(it, p, r) for it, p, r in upgrade_all if it.name in     self.seen_names]
            sep = QLabel(f"  ✨ {RARITY_LABEL.get(upgrade_rarity)} (upgrade {int(UPGRADE_CHANCE*100)}%)")
            sep.setStyleSheet(
                f"color: {RARITY_COLORS.get(upgrade_rarity, '#ccc')};"
                f" font-size: 10px; font-weight: bold; margin-top: 4px;"
            )
            self._vbox.insertWidget(pos, sep); pos += 1
            for it, p, r in up_unseen:
                self._vbox.insertWidget(pos, self._make_row(it, p, r, False)); pos += 1
            for it, p, r in up_seen:
                self._vbox.insertWidget(pos, self._make_row(it, p, r, True));  pos += 1

        self.scroll.verticalScrollBar().setValue(0)


# ──────────────────────────────────────────────────────────────────────
# Custom token button widget
# ──────────────────────────────────────────────────────────────────────

class TokenButton(QFrame):
    clicked = Signal(str)
    hovered = Signal(str)

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

        icon_path = os.path.join(TOKENS_DIR, f"{rarity}.png")
        pixmap = QPixmap(icon_path)
        if not pixmap.isNull():
            self.icon_lbl.setPixmap(pixmap.scaled(
                40, 40,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            ))

    def update_state(self, token_count: int, pool_count: int, debug: bool = False):
        required      = POOL_REQUIRED.get(self.rarity, 20)
        has_tokens    = debug or token_count >= 3
        has_discovery = pool_count >= required
        self._enabled = has_tokens and has_discovery

        color        = RARITY_COLORS.get(self.rarity, "#fff")
        bg           = RARITY_BG.get(self.rarity, "#222")
        border_color = color if self._enabled else "#444"

        self.setStyleSheet(
            f"TokenButton {{ background: {bg}; border: 2px solid {border_color}; border-radius: 8px; }}"
            f"TokenButton:hover {{ border: 3px solid {border_color}; }}"
        )
        self.name_lbl.setStyleSheet(
            f"font-size: 13px; font-weight: bold; color: {color if self._enabled else '#666'};"
        )

        if debug:
            self.tokens_lbl.setStyleSheet("font-size: 11px; color: #4caf50;")
            self.tokens_lbl.setText("∞ tokens")
        else:
            token_color = "#fff" if has_tokens else "#e53935"
            self.tokens_lbl.setStyleSheet(f"font-size: 11px; color: {token_color};")
            self.tokens_lbl.setText(f"{token_count} token{'s' if token_count != 1 else ''}")

        if has_discovery:
            self.discovery_lbl.setStyleSheet("font-size: 10px; color: #4caf50;")
            self.discovery_lbl.setText(f"✔ {pool_count} discovered")
        else:
            self.discovery_lbl.setStyleSheet("font-size: 10px; color: #888;")
            self.discovery_lbl.setText(f"{pool_count} / {required} discovered")

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

    def enterEvent(self, event):
        self.hovered.emit(self.rarity)
        super().enterEvent(event)


# ──────────────────────────────────────────────────────────────────────
# Reroll dialog — opens after spending tokens
# ──────────────────────────────────────────────────────────────────────

class RerollDialog(QDialog):
    def __init__(self, parent, rarity: str, effective_rarity: str,
                 pool_items: list, items_pool: dict,
                 sav_path: str, inventories: dict,
                 loaded_mtime: float | None = None,
                 debug: bool = False):
        super().__init__(parent)
        label = RARITY_LABEL.get(rarity, rarity.capitalize())
        self.setWindowTitle(f"Token Shop — {label}")
        self.setMinimumWidth(760)
        self.setMinimumHeight(540)
        self.setWindowModality(Qt.WindowModality.ApplicationModal)

        self.base_rarity  = rarity
        self.pool_items   = pool_items
        self.items_pool   = items_pool
        self.sav_path     = sav_path
        self.inventories  = inventories
        self.loaded_mtime = loaded_mtime
        self.debug        = debug

        self.current_item: Item | None = None
        self.rerolls_left: int = MAX_REROLLS
        self.seen_names: set[str] = set()

        self._build_ui()

        if self.debug:
            self.loot_panel.item_clicked.connect(self._force_pick)

        self._pick_item(effective_rarity, fallback=rarity)

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------

    def _build_ui(self):
        root = QHBoxLayout(self)
        root.setSpacing(0)
        root.setContentsMargins(0, 0, 0, 0)

        # ── Left panel: loot list ──────────────────────────────────────
        left = QFrame()
        left.setFixedWidth(300)
        left.setStyleSheet(
            "QFrame { background: #161616; border-right: 1px solid #2a2a2a; }"
        )
        left_vbox = QVBoxLayout(left)
        left_vbox.setContentsMargins(12, 14, 12, 14)
        left_vbox.setSpacing(6)

        header = QLabel("Loots possibles")
        header.setStyleSheet(
            "color: #aaa; font-size: 13px; font-weight: bold;"
            " border: none; background: transparent;"
        )
        left_vbox.addWidget(header)

        self.loot_panel = LootPreviewPanel(self.pool_items, debug=self.debug, parent=self)
        left_vbox.addWidget(self.loot_panel)

        root.addWidget(left)

        # ── Right panel: item preview + actions ───────────────────────
        right = QFrame()
        right.setStyleSheet("QFrame { background: #1e1e1e; border: none; }")
        right_vbox = QVBoxLayout(right)
        right_vbox.setContentsMargins(28, 28, 28, 28)
        right_vbox.setSpacing(14)

        # Icon
        icon_wrap = QWidget()
        icon_wrap.setStyleSheet("background: transparent;")
        iw = QHBoxLayout(icon_wrap)
        iw.setContentsMargins(0, 0, 0, 0)
        iw.addStretch()
        self.item_icon = QLabel()
        self.item_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.item_icon.setFixedSize(96, 96)
        iw.addWidget(self.item_icon)
        iw.addStretch()
        right_vbox.addWidget(icon_wrap)

        # Name
        self.item_name = QLabel("—")
        self.item_name.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.item_name.setStyleSheet(
            "font-size: 18px; font-weight: bold; color: #fff; background: transparent;"
        )
        self.item_name.setWordWrap(True)
        right_vbox.addWidget(self.item_name)

        # Info (rarity / category / description)
        self.item_info = QLabel()
        self.item_info.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.item_info.setWordWrap(True)
        self.item_info.setTextFormat(Qt.TextFormat.RichText)
        self.item_info.setStyleSheet("background: transparent;")
        right_vbox.addWidget(self.item_info)

        right_vbox.addStretch()

        # Buttons
        self.reroll_btn = QPushButton()
        self.reroll_btn.setVisible(False)
        self.reroll_btn.setStyleSheet(
            "QPushButton { font-size: 13px; font-weight: bold; padding: 8px 16px;"
            " background: #e65100; color: white; border: none; border-radius: 4px; }"
            "QPushButton:hover { background: #bf360c; }"
            "QPushButton:disabled { background: #3a3a3a; color: #666; }"
        )
        self.reroll_btn.clicked.connect(self._reroll)
        right_vbox.addWidget(self.reroll_btn)

        self.take_btn = QPushButton("➕ Ajouter au Storage")
        self.take_btn.setVisible(False)
        self.take_btn.setStyleSheet(
            "QPushButton { font-size: 13px; font-weight: bold; padding: 8px 16px;"
            " background: #2e7d32; color: white; border: none; border-radius: 4px; }"
            "QPushButton:hover { background: #1b5e20; }"
        )
        self.take_btn.clicked.connect(self._take_item)
        right_vbox.addWidget(self.take_btn)

        root.addWidget(right, stretch=1)


    # ------------------------------------------------------------------
    # Item picking
    # ------------------------------------------------------------------

    def _candidates(self, rarity: str, exclude_seen: bool = True) -> list[Item]:
        return [
            it for it in self.pool_items
            if getattr(it, "rarity", None) == rarity
            and (not exclude_seen or it.name not in self.seen_names)
        ]

    def _pick_item(self, rarity: str, fallback: str | None = None):
        candidates = self._candidates(rarity)
        if not candidates and fallback and fallback != rarity:
            candidates = self._candidates(fallback)
        if not candidates:
            candidates = self._candidates(rarity, exclude_seen=False)
            if not candidates and fallback and fallback != rarity:
                candidates = self._candidates(fallback, exclude_seen=False)
        if not candidates:
            self.current_item = None
            self.item_name.setText("Aucun item disponible pour cette rareté")
            self.item_info.clear()
            self.item_icon.clear()
            self.reroll_btn.setVisible(False)
            self.take_btn.setVisible(False)
            return

        self.current_item = random.choice(candidates)
        self.seen_names.add(self.current_item.name)

        # Victory sound when the item is from a higher rarity (upgrade)
        if getattr(self.current_item, "rarity", None) != self.base_rarity:
            play_victory_fx()

        self._display_item()
        self._refresh_action_btns()
        # Sync loot list
        self.loot_panel.show_rarity(self.base_rarity, self.seen_names)

    def _display_item(self):
        item    = self.current_item
        details = item.details or {}

        rarity_raw = details.get("rarity", "common") or "common"
        bg_color   = RARITY_BG.get(rarity_raw, "#222")
        self.item_icon.setStyleSheet(
            f"background-color: {bg_color}; border-radius: 8px;"
        )
        self.item_icon.setPixmap(
            svg_to_pixmap(os.path.join(ICON_DIR, item.icon_name or ""), 80)
        )

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
        lines.append(f"<b>Category:</b> {item.category or '—'}")
        desc = details.get("desc_resolved")
        if desc:
            for key, val in details.items():
                if key not in ("name", "desc", "name_resolved", "desc_resolved", "rarity", "kind"):
                    try:
                        desc = desc.replace(f"{{{key}}}", str(val))
                    except Exception:
                        pass
            lines.append(f'<br><span style="color:#ddd; font-size:13px;"><i>{desc}</i></span>')
        self.item_info.setText("<br>".join(lines))

    def _refresh_action_btns(self):
        unseen = len(self._candidates(self.base_rarity))
        self.reroll_btn.setToolTip(
            "Tous les items uniques ont été proposés" if unseen == 0
            else f"{unseen} item(s) non encore vus"
        )
        self.reroll_btn.setText(
            f"🎲 Reroll ({self.rerolls_left} restant{'s' if self.rerolls_left != 1 else ''})"
        )
        self.reroll_btn.setEnabled(self.rerolls_left > 0)
        self.reroll_btn.setVisible(True)
        self.take_btn.setVisible(True)

    # ------------------------------------------------------------------
    # Reroll
    # ------------------------------------------------------------------

    def _force_pick(self, item: Item):
        """Debug only — immediately set the clicked item as the current pick (no reroll consumed)."""
        if item.name in self.seen_names:
            return
        self.current_item = item
        self.seen_names.add(item.name)
        if getattr(item, "rarity", None) != self.base_rarity:
            play_victory_fx()
        self._display_item()
        self._refresh_action_btns()
        self.loot_panel.show_rarity(self.base_rarity, self.seen_names)

    def _reroll(self):
        if self.rerolls_left <= 0 or not self.current_item:
            return
        self.rerolls_left -= 1
        effective = self.base_rarity
        upgrade   = RARITY_UPGRADE.get(self.base_rarity)
        if upgrade and random.random() < UPGRADE_CHANCE:
            effective = upgrade
        self._pick_item(effective, fallback=self.base_rarity)

    # ------------------------------------------------------------------
    # Take item
    # ------------------------------------------------------------------

    def _take_item(self):
        if not self.current_item:
            return

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


# ──────────────────────────────────────────────────────────────────────
# Main token shop dialog  (rarity buttons  +  hover loot preview)
# ──────────────────────────────────────────────────────────────────────

class TokenShopDialog(QDialog):
    def __init__(self, parent, tokens: dict, pool_items: list, items_pool: dict,
                 sav_path: str, inventories: dict, loaded_mtime: float | None = None,
                 debug: bool = False):
        super().__init__(parent)
        self.setWindowTitle("Token Shop")
        self.setMinimumWidth(680)
        self.setMinimumHeight(480)
        self.setWindowModality(Qt.WindowModality.ApplicationModal)

        self.tokens       = dict(tokens)
        self.pool_items   = pool_items
        self.items_pool   = items_pool
        self.sav_path     = sav_path
        self.inventories  = inventories
        self.loaded_mtime = loaded_mtime
        self.debug        = debug

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

        subtitle = QLabel("Dépensez 3 tokens · 3 % de chance d'obtenir la rareté supérieure")
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        subtitle.setStyleSheet("color: #777; font-size: 12px;")
        layout.addWidget(subtitle)

        # Token buttons row
        token_row = QWidget()
        token_layout = QHBoxLayout(token_row)
        token_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        token_layout.setSpacing(12)
        self.token_btns: dict[str, TokenButton] = {}
        for rarity in RARITIES_IN_SHOP:
            btn = TokenButton(rarity, self)
            btn.clicked.connect(self._spend_tokens)
            btn.hovered.connect(self._on_hover)
            self.token_btns[rarity] = btn
            token_layout.addWidget(btn)
        layout.addWidget(token_row)

        # Loot preview panel (fills remaining height)
        preview_frame = QFrame()
        preview_frame.setStyleSheet(
            "QFrame { background: #1a1a1a; border: 1px solid #333; border-radius: 6px; }"
        )
        pf_vbox = QVBoxLayout(preview_frame)
        pf_vbox.setContentsMargins(10, 8, 10, 8)
        pf_vbox.setSpacing(0)
        self.loot_panel = LootPreviewPanel(self.pool_items, parent=self)
        pf_vbox.addWidget(self.loot_panel)
        layout.addWidget(preview_frame, stretch=1)

    # ------------------------------------------------------------------

    def _on_hover(self, rarity: str):
        # Preview with no seen items (pure probability display)
        self.loot_panel.show_rarity(rarity, set())

    def _pool_count(self, rarity: str) -> int:
        return sum(1 for it in self.pool_items if getattr(it, "rarity", None) == rarity)

    def _update_token_buttons(self):
        for rarity, btn in self.token_btns.items():
            btn.update_state(
                token_count=self.tokens.get(rarity, 0),
                pool_count=self._pool_count(rarity),
                debug=self.debug,
            )

    def _spend_tokens(self, rarity: str):
        if not self.debug and self.tokens.get(rarity, 0) < 3:
            return

        label = RARITY_LABEL.get(rarity, rarity.capitalize())
        reply = QMessageBox.question(
            self, "Confirmation",
            f"Dépenser 3 tokens {label} ?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        if not self.debug:
            self.tokens[rarity] -= 3
            mtime = self.loaded_mtime if self.loaded_mtime is not None else (
                os.path.getmtime(self.sav_path) if os.path.exists(self.sav_path) else 0.0
            )
            save_tokens(self.tokens, mtime)
        self._update_token_buttons()

        # Determine effective rarity (upgrade chance)
        effective = rarity
        upgrade   = RARITY_UPGRADE.get(rarity)
        if upgrade and random.random() < UPGRADE_CHANCE:
            effective = upgrade

        dlg = RerollDialog(
            parent=self,
            rarity=rarity,
            effective_rarity=effective,
            pool_items=self.pool_items,
            items_pool=self.items_pool,
            sav_path=self.sav_path,
            inventories=self.inventories,
            loaded_mtime=self.loaded_mtime,
            debug=self.debug,
        )
        dlg.exec()

        # Refresh hover preview for this rarity after dialog closes
        self._on_hover(rarity)

