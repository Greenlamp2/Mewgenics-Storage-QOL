"""ui/cat_manager.py — Cat Manager window for browsing all cats in the save."""

import os
import re

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QScrollArea, QFrame,
    QSplitter, QPushButton, QGridLayout,
)

from catalogs.stat_catalog import STAT_NAMES
from catalogs.ability_catalog import _ABILITY_LOOKUP

_GENDER_SYMBOL = {"male": "♂", "female": "♀", "?": "⚥"}
_GENDER_COLOR  = {"male": "#5b9cf6", "female": "#f47abf", "?": "#aaaaaa"}
_STATUS_COLOR  = {"In House": "#4caf50", "Adventure": "#ff9800", "Gone": "#666666"}
_STATUS_ICON   = {"In House": "🏠", "Adventure": "⚔️", "Gone": "💨"}

STAT_DISPLAY_COLORS = {
    "STR": "#e05050", "DEX": "#50c050", "CON": "#6090e0",
    "INT": "#c0a030", "SPD": "#a060d0", "CHA": "#e08040", "LCK": "#50c0c0",
}

# ------------------------------------------------------------------
# Ability description lookup
# ------------------------------------------------------------------

def _ability_desc(name: str) -> str:
    """Return description from catalog, or empty string if unknown."""
    key = re.sub(r'[^a-z0-9]', '', (name or "").lower())
    return _ABILITY_LOOKUP.get(key, "")


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

def _fmt_pct(v) -> str:
    if v is None:
        return "—"
    return f"{v * 100:.0f} %"


def _names(cats) -> str:
    if not cats:
        return "—"
    return ", ".join(c.name for c in cats)


def _section_label(text: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setStyleSheet(
        "color: #e0c060; font-size: 12px; font-weight: bold;"
        " border-bottom: 1px solid #444; padding-bottom: 3px; background: transparent;"
    )
    return lbl


def _info_row(label: str, value: str, value_color: str = "#e0e0e0") -> QWidget:
    w = QWidget()
    w.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, False)
    lay = QHBoxLayout(w)
    lay.setContentsMargins(0, 1, 0, 1)
    lay.setSpacing(6)
    k = QLabel(label)
    k.setStyleSheet("color: #888; font-size: 12px; background: transparent;")
    k.setFixedWidth(100)
    v = QLabel(value)
    v.setWordWrap(True)
    v.setStyleSheet(f"color: {value_color}; font-size: 12px; background: transparent;")
    lay.addWidget(k)
    lay.addWidget(v, 1)
    return w


def _ability_entry(name: str, desc: str, bg: str, name_color: str, desc_color: str = "#999") -> QWidget:
    """A single ability/mutation row: name on the left, description on the right (or below if long)."""
    w = QWidget()
    w.setStyleSheet(f"background: {bg}; border: 1px solid {name_color}22; border-radius: 5px;")
    lay = QVBoxLayout(w)
    lay.setContentsMargins(8, 5, 8, 5)
    lay.setSpacing(2)

    name_lbl = QLabel(name)
    name_lbl.setStyleSheet(
        f"color: {name_color}; font-size: 12px; font-weight: bold; background: transparent;"
        " border: none;"
    )
    lay.addWidget(name_lbl)

    if desc:
        desc_lbl = QLabel(desc)
        desc_lbl.setWordWrap(True)
        desc_lbl.setStyleSheet(
            f"color: {desc_color}; font-size: 11px; background: transparent; border: none;"
        )
        lay.addWidget(desc_lbl)

    return w


def _ability_list(
    items,          # list[str]  OR  list[tuple[str, str]]
    bg: str,
    name_color: str,
    desc_color: str = "#999",
    use_catalog: bool = True,
) -> QWidget:
    """
    Build a vertical list of _ability_entry widgets.
    *items* can be:
      - list[str]          → look up description from catalog if use_catalog=True
      - list[(name, desc)] → use provided description directly
    """
    w = QWidget()
    w.setStyleSheet("background: transparent;")
    lay = QVBoxLayout(w)
    lay.setContentsMargins(0, 0, 0, 0)
    lay.setSpacing(4)

    if not items:
        none_lbl = QLabel("—")
        none_lbl.setStyleSheet("color: #666; font-size: 12px; background: transparent;")
        lay.addWidget(none_lbl)
        return w

    for entry in items:
        if isinstance(entry, tuple):
            name, desc = entry
        else:
            name = entry
            desc = _ability_desc(name) if use_catalog else ""
        lay.addWidget(_ability_entry(name, desc, bg, name_color, desc_color))

    return w


# ------------------------------------------------------------------
# Cat list card
# ------------------------------------------------------------------

class _CatCard(QFrame):
    """Compact clickable cat card shown in the list."""
    selected = Signal(object)   # emits Cat

    _NORMAL = (
        "QFrame { background: #1c1c1c; border: 1px solid #333; border-radius: 6px; }"
    )
    _HOVER = (
        "QFrame { background: #242424; border: 1px solid #555; border-radius: 6px; }"
    )
    _ACTIVE = (
        "QFrame { background: #1a2a1a; border: 1px solid #4caf50; border-radius: 6px; }"
    )

    def __init__(self, cat, parent=None):
        super().__init__(parent)
        self._cat = cat
        self.setFixedHeight(58)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setStyleSheet(self._NORMAL)

        lay = QHBoxLayout(self)
        lay.setContentsMargins(10, 6, 10, 6)
        lay.setSpacing(8)

        # Gender pill
        g = cat.gender
        g_lbl = QLabel(_GENDER_SYMBOL.get(g, "?"))
        g_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        g_lbl.setFixedSize(28, 28)
        g_lbl.setStyleSheet(
            f"background: transparent; color: {_GENDER_COLOR.get(g, '#aaa')};"
            f" font-size: 18px; font-weight: bold;"
        )
        lay.addWidget(g_lbl)

        # Name + location
        center = QVBoxLayout()
        center.setSpacing(2)
        name_lbl = QLabel(cat.name or "(unknown)")
        name_lbl.setStyleSheet(
            "color: #e8e8e8; font-size: 13px; font-weight: bold; background: transparent;"
        )
        center.addWidget(name_lbl)

        status = cat.status
        room_text = cat.room if cat.room and cat.room != status else status
        sub_lbl = QLabel(f"{_STATUS_ICON.get(status, '')}  {room_text}")
        sub_lbl.setStyleSheet(
            f"color: {_STATUS_COLOR.get(status, '#888')}; font-size: 11px; background: transparent;"
        )
        center.addWidget(sub_lbl)
        lay.addLayout(center, 1)

    def set_active(self, active: bool):
        self.setStyleSheet(self._ACTIVE if active else self._NORMAL)

    def enterEvent(self, event):
        if self.styleSheet() != self._ACTIVE:
            self.setStyleSheet(self._HOVER)
        super().enterEvent(event)

    def leaveEvent(self, event):
        if self.styleSheet() != self._ACTIVE:
            self.setStyleSheet(self._NORMAL)
        super().leaveEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.selected.emit(self._cat)
        super().mousePressEvent(event)


# ------------------------------------------------------------------
# Detail panel
# ------------------------------------------------------------------

class _CatDetail(QScrollArea):
    """Right-side scrollable detail panel for a selected cat."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWidgetResizable(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setStyleSheet("QScrollArea { border: none; background: #111; }")

        self._root = QWidget()
        self._root.setStyleSheet("background: #111;")
        self._layout = QVBoxLayout(self._root)
        self._layout.setContentsMargins(16, 16, 16, 16)
        self._layout.setSpacing(12)
        self.setWidget(self._root)

        self._empty_lbl = QLabel("← Select a cat")
        self._empty_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._empty_lbl.setStyleSheet("color: #555; font-size: 16px;")
        self._layout.addWidget(self._empty_lbl)
        self._layout.addStretch()

    # ── public ───────────────────────────────────────────────────────

    def show_cat(self, cat) -> None:
        """Rebuild the detail panel for *cat*."""
        while self._layout.count():
            item = self._layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        # ── Header ───────────────────────────────────────────────────
        header = QWidget()
        h_lay = QVBoxLayout(header)
        h_lay.setContentsMargins(0, 0, 0, 4)
        h_lay.setSpacing(4)

        name_lbl = QLabel(cat.name or "(unknown)")
        name_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        name_lbl.setWordWrap(True)
        name_lbl.setStyleSheet(
            "color: #f0f0f0; font-size: 20px; font-weight: bold; background: transparent;"
        )
        h_lay.addWidget(name_lbl)

        # Special flags
        flags_row = QHBoxLayout()
        flags_row.setContentsMargins(0, 0, 0, 0)
        flags_row.setSpacing(6)
        flags_row.setAlignment(Qt.AlignmentFlag.AlignCenter)
        if getattr(cat, "is_blacklisted", False):
            bl = QLabel("🚫 Blacklisted")
            bl.setStyleSheet(
                "background: #3a0a0a; color: #ff6060; font-size: 11px; font-weight: bold;"
                " border: 1px solid #882222; border-radius: 4px; padding: 2px 8px;"
            )
            flags_row.addWidget(bl)
        if getattr(cat, "must_breed", False):
            mb = QLabel("💕 Must Breed")
            mb.setStyleSheet(
                "background: #2a1a2a; color: #ff99cc; font-size: 11px; font-weight: bold;"
                " border: 1px solid #884466; border-radius: 4px; padding: 2px 8px;"
            )
            flags_row.addWidget(mb)
        if flags_row.count():
            fw = QWidget()
            fw.setLayout(flags_row)
            h_lay.addWidget(fw)

        status = cat.status
        s_color = _STATUS_COLOR.get(status, "#888")
        row2 = QHBoxLayout()
        row2.setAlignment(Qt.AlignmentFlag.AlignCenter)
        row2.setSpacing(10)

        status_lbl = QLabel(f"{_STATUS_ICON.get(status, '')}  {status}")
        status_lbl.setStyleSheet(f"color: {s_color}; font-size: 13px; background: transparent;")
        row2.addWidget(status_lbl)

        g = cat.gender
        gender_lbl = QLabel(f"{_GENDER_SYMBOL.get(g, '?')} {g.capitalize()}")
        gender_lbl.setStyleSheet(
            f"color: {_GENDER_COLOR.get(g, '#aaa')}; font-size: 13px; background: transparent;"
        )
        row2.addWidget(gender_lbl)

        if cat.age is not None:
            age_lbl = QLabel(f"🕐 {cat.age}d")
            age_lbl.setStyleSheet("color: #aaa; font-size: 12px; background: transparent;")
            row2.addWidget(age_lbl)

        row2_w = QWidget()
        row2_w.setLayout(row2)
        h_lay.addWidget(row2_w)

        if cat.collar:
            collar_lbl = QLabel(f"🎀 {cat.collar}")
            collar_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            collar_lbl.setStyleSheet("color: #cc88cc; font-size: 12px; background: transparent;")
            h_lay.addWidget(collar_lbl)

        self._layout.addWidget(header)
        self._layout.addWidget(_hsep())

        # ── Location ─────────────────────────────────────────────────
        if cat.room and cat.room not in (cat.status, ""):
            self._layout.addWidget(_info_row("Room", cat.room))
            self._layout.addWidget(_hsep())

        # ── Stats ─────────────────────────────────────────────────────
        self._layout.addWidget(_section_label("📊  Stats"))
        self._layout.addWidget(self._build_stats_widget(cat))
        self._layout.addWidget(_hsep())

        # ── Personality ───────────────────────────────────────────────
        self._layout.addWidget(_section_label("🧠  Personality"))
        pers_row = QHBoxLayout()
        pers_row.setSpacing(8)
        for label, val, color in [
            ("Aggression", _fmt_pct(cat.aggression), "#e05050"),
            ("Libido",     _fmt_pct(cat.libido),     "#e090c0"),
            ("Inbredness", _fmt_pct(cat.inbredness), "#c0a030"),
        ]:
            pill = QLabel(f"<b style='color:{color}'>{label}</b><br>{val}")
            pill.setAlignment(Qt.AlignmentFlag.AlignCenter)
            pill.setStyleSheet(
                f"background: #1c1c1c; border: 1px solid #333; border-radius: 5px;"
                f" padding: 4px 8px; font-size: 11px; color: #ccc;"
            )
            pers_row.addWidget(pill, 1)
        pers_w = QWidget()
        pers_w.setLayout(pers_row)
        self._layout.addWidget(pers_w)
        self._layout.addWidget(_hsep())

        # ── Abilities ─────────────────────────────────────────────────
        self._layout.addWidget(_section_label("⚔️  Abilities"))
        self._layout.addWidget(
            _ability_list(cat.abilities, "#131d2a", "#5b9cf6", use_catalog=True)
        )

        if cat.passive_abilities:
            self._layout.addWidget(_section_label("●  Passives"))
            self._layout.addWidget(
                _ability_list(cat.passive_abilities, "#13261a", "#66cc66", use_catalog=True)
            )

        if cat.disorders:
            self._layout.addWidget(_section_label("⚠  Disorders"))
            self._layout.addWidget(
                _ability_list(cat.disorders, "#261313", "#e05050", use_catalog=True)
            )

        equipment = getattr(cat, "equipment", [])
        if equipment:
            self._layout.addWidget(_section_label("🎒  Equipment"))
            self._layout.addWidget(
                _ability_list(equipment, "#1a1a2a", "#b0a0e0", use_catalog=False)
            )

        # ── Mutations / Defects ───────────────────────────────────────
        mutation_chip_items = getattr(cat, "mutation_chip_items", [])
        defect_chip_items   = getattr(cat, "defect_chip_items",   [])

        if mutation_chip_items or defect_chip_items:
            self._layout.addWidget(_hsep())
            if mutation_chip_items:
                self._layout.addWidget(_section_label("🧬  Mutations"))
                self._layout.addWidget(
                    _ability_list(mutation_chip_items, "#131c26", "#80bbdd",
                                  desc_color="#7aaacc", use_catalog=False)
                )
            if defect_chip_items:
                self._layout.addWidget(_section_label("⚡  Defects"))
                self._layout.addWidget(
                    _ability_list(defect_chip_items, "#261c13", "#e0a030",
                                  desc_color="#b07820", use_catalog=False)
                )

        # ── Family ────────────────────────────────────────────────────
        self._layout.addWidget(_hsep())
        self._layout.addWidget(_section_label("👨‍👩‍👧  Family"))
        pa = cat.parent_a.name if cat.parent_a else "—"
        pb = cat.parent_b.name if cat.parent_b else "—"
        self._layout.addWidget(_info_row("Parent A",  pa,                    "#b0c8f0"))
        self._layout.addWidget(_info_row("Parent B",  pb,                    "#b0c8f0"))
        self._layout.addWidget(_info_row("Children",  _names(cat.children),  "#c8f0b0"))
        self._layout.addWidget(_info_row("Lovers",    _names(cat.lovers),    "#f0b0c8"))
        self._layout.addWidget(_info_row("Haters",    _names(cat.haters),    "#f0b0b0"))

        self._layout.addStretch()

    def clear(self):
        while self._layout.count():
            item = self._layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        empty = QLabel("← Select a cat")
        empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        empty.setStyleSheet("color: #555; font-size: 16px; background: transparent;")
        self._layout.addWidget(empty)
        self._layout.addStretch()

    # ── builders ─────────────────────────────────────────────────────

    @staticmethod
    def _build_stats_widget(cat) -> QWidget:
        w = QWidget()
        w.setStyleSheet("background: transparent;")
        grid = QGridLayout(w)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setSpacing(6)

        for col, stat in enumerate(STAT_NAMES):
            base  = cat.stat_base[col]  if col < len(cat.stat_base) else 0
            total = list(cat.total_stats.values())[col] if col < len(cat.total_stats) else base
            color = STAT_DISPLAY_COLORS.get(stat, "#ccc")
            diff  = total - base

            name_lbl = QLabel(stat)
            name_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            name_lbl.setStyleSheet(
                f"color: {color}; font-size: 10px; font-weight: bold; background: transparent;"
            )
            grid.addWidget(name_lbl, 0, col)

            diff_str = f" ({'+' if diff >= 0 else ''}{diff})" if diff != 0 else ""
            val_lbl = QLabel(f"{base}{diff_str}")
            val_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            val_lbl.setStyleSheet(
                f"color: {'#88ee88' if diff > 0 else '#ee8888' if diff < 0 else '#e0e0e0'};"
                f" font-size: 13px; font-weight: bold; background: #1e1e1e;"
                f" border: 1px solid #333; border-radius: 4px; padding: 2px 4px;"
            )
            grid.addWidget(val_lbl, 1, col)

        return w


# ------------------------------------------------------------------
# Horizontal separator helper
# ------------------------------------------------------------------

def _hsep() -> QFrame:
    sep = QFrame()
    sep.setFrameShape(QFrame.Shape.HLine)
    sep.setStyleSheet("QFrame { color: #2a2a2a; }")
    return sep


# ------------------------------------------------------------------
# Main Cat Manager window
# ------------------------------------------------------------------

class CatManagerWindow(QWidget):
    """Standalone window showing all cats parsed from the save file."""

    def __init__(self, cats: list, parent=None):
        super().__init__(parent, Qt.WindowType.Window)
        self.setWindowTitle("Cat Manager")
        _icon = os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            "assets", "icons", "tokens", "very_rare.png",
        )
        self.setWindowIcon(QIcon(_icon))
        self.resize(1050, 680)
        self.setStyleSheet("QWidget { background: #111111; color: #dddddd; }")

        self._cats = cats
        self._active_card: _CatCard | None = None

        # ── Filter bar ───────────────────────────────────────────────
        filter_bar = QWidget()
        filter_bar.setStyleSheet("QWidget { background: #171717; border-bottom: 1px solid #333; }")
        fb_lay = QHBoxLayout(filter_bar)
        fb_lay.setContentsMargins(10, 6, 10, 6)
        fb_lay.setSpacing(6)

        self._filter = "house"
        _btn_style_active = (
            "QPushButton { font-size: 12px; padding: 3px 12px; border: 1px solid #4caf50;"
            " border-radius: 4px; background: #1a2d1a; color: #4caf50; font-weight: bold; }"
        )
        _btn_style = (
            "QPushButton { font-size: 12px; padding: 3px 12px; border: 1px solid #444;"
            " border-radius: 4px; background: #1e1e1e; color: #aaa; }"
            "QPushButton:hover { background: #282828; color: #ccc; }"
        )
        self._filter_btns: dict[str, QPushButton] = {}
        self._filter_btn_active_style = _btn_style_active
        self._filter_btn_normal_style = _btn_style

        # Only "In House" and "Adventure" — no "All"
        for key, label in [("house", "🏠 In House"), ("adventure", "⚔️ Adventure")]:
            btn = QPushButton(label)
            btn.setStyleSheet(_btn_style_active if key == self._filter else _btn_style)
            btn.clicked.connect(lambda _=False, k=key: self._set_filter(k))
            self._filter_btns[key] = btn
            fb_lay.addWidget(btn)

        self._count_lbl = QLabel()
        self._count_lbl.setStyleSheet("color: #666; font-size: 12px; background: transparent;")
        fb_lay.addWidget(self._count_lbl)
        fb_lay.addStretch()

        # ── Splitter: list | detail ───────────────────────────────────
        splitter = QSplitter(Qt.Orientation.Horizontal)

        self._list_container = QWidget()
        self._list_container.setStyleSheet("background: #141414;")
        self._list_layout = QVBoxLayout(self._list_container)
        self._list_layout.setContentsMargins(8, 8, 8, 8)
        self._list_layout.setSpacing(5)
        self._list_layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        list_scroll = QScrollArea()
        list_scroll.setWidgetResizable(True)
        list_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        list_scroll.setStyleSheet("QScrollArea { border: none; background: #141414; }")
        list_scroll.setWidget(self._list_container)

        self._detail = _CatDetail()

        left_frame = QWidget()
        lf_lay = QVBoxLayout(left_frame)
        lf_lay.setContentsMargins(0, 0, 0, 0)
        lf_lay.setSpacing(0)
        lf_lay.addWidget(list_scroll)

        splitter.addWidget(left_frame)
        splitter.addWidget(self._detail)
        splitter.setSizes([320, 730])
        splitter.setHandleWidth(4)

        root_lay = QVBoxLayout(self)
        root_lay.setContentsMargins(0, 0, 0, 0)
        root_lay.setSpacing(0)
        root_lay.addWidget(filter_bar)
        root_lay.addWidget(splitter, 1)

        self._rebuild_list()

    # ── Filter ───────────────────────────────────────────────────────

    def _set_filter(self, key: str):
        self._filter = key
        for k, btn in self._filter_btns.items():
            btn.setStyleSheet(
                self._filter_btn_active_style if k == key
                else self._filter_btn_normal_style
            )
        self._rebuild_list()

    def _filtered_cats(self) -> list:
        if self._filter == "house":
            return [c for c in self._cats if c.status == "In House"]
        if self._filter == "adventure":
            return [c for c in self._cats if c.status == "Adventure"]
        return list(self._cats)

    # ── List ─────────────────────────────────────────────────────────

    def _rebuild_list(self):
        while self._list_layout.count():
            item = self._list_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        self._active_card = None
        self._detail.clear()

        cats = self._filtered_cats()
        self._count_lbl.setText(f"{len(cats)} cat(s)")

        if not cats:
            empty = QLabel("No cats found.")
            empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
            empty.setStyleSheet("color: #555; font-size: 13px; padding: 30px;")
            self._list_layout.addWidget(empty)
            return

        cats_sorted = sorted(cats, key=lambda c: (c.name or ""))

        for cat in cats_sorted:
            card = _CatCard(cat)
            card.selected.connect(self._on_cat_selected)
            self._list_layout.addWidget(card)

        self._list_layout.addStretch()

    def _on_cat_selected(self, cat):
        if self._active_card is not None:
            self._active_card.set_active(False)

        for i in range(self._list_layout.count()):
            item = self._list_layout.itemAt(i)
            if item and item.widget() and isinstance(item.widget(), _CatCard):
                card: _CatCard = item.widget()
                if card._cat is cat:
                    card.set_active(True)
                    self._active_card = card
                    break

        self._detail.show_cat(cat)

    # ── Public refresh ────────────────────────────────────────────────

    def refresh(self, cats: list):
        """Update the cat list (called when the main window reloads)."""
        self._cats = cats
        self._rebuild_list()

