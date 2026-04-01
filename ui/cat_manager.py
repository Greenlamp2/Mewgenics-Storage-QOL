"""ui/cat_manager.py — Cat Manager window for browsing all cats in the save."""

import os
import re

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QScrollArea, QFrame,
    QSplitter, QPushButton, QGridLayout, QInputDialog, QMessageBox,
    QComboBox, QLineEdit, QSpinBox,
)

from catalogs.stat_catalog import STAT_NAMES
from catalogs.ability_catalog import _ABILITY_LOOKUP

_GENDER_SYMBOL = {"male": "♂", "female": "♀", "?": "⚥"}
_GENDER_COLOR  = {"male": "#5b9cf6", "female": "#f47abf", "?": "#aaaaaa"}
_STATUS_COLOR  = {"In House": "#4caf50", "Adventure": "#ff9800", "Gone": "#666666", "In Bank": "#7b68ee"}
_STATUS_ICON   = {"In House": "🏠", "Adventure": "⚔️", "Gone": "💨", "In Bank": "🏦"}

ROOM_DISPLAY_NAMES: dict[str, str] = {
    "Floor1_Large": "RDC Gauche",
    "Floor1_Small": "RDC Droite",
    "Floor2_Small": "Etage Gauche",
    "Floor2_Large": "Etage Droite",
    "Attic":        "Grenier",
}


def _room_display(room_name: str) -> str:
    """Return a human-friendly display name for a room key."""
    return ROOM_DISPLAY_NAMES.get(room_name, room_name)

STAT_DISPLAY_COLORS = {
    "STR": "#e05050", "DEX": "#50c050", "CON": "#6090e0",
    "INT": "#c0a030", "SPD": "#a060d0", "CHA": "#e08040", "LCK": "#50c0c0",
}

# ------------------------------------------------------------------
# Query-builder UI constants
# ------------------------------------------------------------------

_FILTER_TYPE_LABELS: dict[str, str] = {
    "abilities":      "⚔️ Abilities",
    "passives":       "● Passives",
    "mutation":       "🧬 Mutation name",
    "mutation_count": "🧬 Mutation count",
    "gender":         "♂♀ Gender",
    "sexuality":      "💕 Sexuality",
    "defects":        "⚡ Defect name",
    "defects_count":  "⚡ Defect count",
    "disorder":       "⚠ Disorder",
    "room":           "🏠 Room",
}

_OPERATOR_LABELS: dict[str, str] = {
    "contains":     "contains",
    "not_contains": "not contains",
    "any_of":       "any of (comma-sep)",
    "none_of":      "none of (comma-sep)",
    "is_empty":     "is empty",
    "is_not_empty": "is not empty",
    "eq":  "=",
    "ne":  "≠",
    "lt":  "<",
    "lte": "≤",
    "gt":  ">",
    "gte": "≥",
}

# Fields whose value input is a fixed dropdown instead of a text box
_STRING_FIELD_CHOICES: dict[str, list[str]] = {
    "gender":    ["male", "female", "?"],
    "sexuality": ["straight", "gay", "bi"],
}

# Operators that take no value input at all
_NO_VALUE_OPERATORS: frozenset[str] = frozenset({"is_empty", "is_not_empty"})


def _get_query_presets_path() -> str:
    """Return the path to cat_query_presets.json in the custom save folder."""
    try:
        from utils.save_manager import CUSTOM_FOLDER
        if CUSTOM_FOLDER:
            return os.path.join(CUSTOM_FOLDER, "cat_query_presets.json")
    except Exception:
        pass
    return ""


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
    """A single ability/mutation row: name on top, description below."""
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
    items,
    bg: str,
    name_color: str,
    desc_color: str = "#999",
    use_catalog: bool = True,
) -> QWidget:
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
# Room header (shown above each room group in the list)
# ------------------------------------------------------------------

class _RoomHeader(QWidget):
    """Sticky section header showing a room name and a 'Select all' toggle."""
    select_all_clicked = Signal(str)   # emits room_name

    def __init__(self, room_name: str, count: int, all_selected: bool = False, parent=None):
        super().__init__(parent)
        self._room_name = room_name
        self.setStyleSheet(
            "QWidget { background: #1e1e1e; border-radius: 4px; border: 1px solid #2a2a2a; }"
        )

        lay = QHBoxLayout(self)
        lay.setContentsMargins(10, 4, 8, 4)
        lay.setSpacing(6)

        lbl = QLabel(f"🏠  {_room_display(room_name)}  ({count})")
        lbl.setStyleSheet(
            "color: #777; font-size: 11px; font-weight: bold;"
            " background: transparent; border: none;"
        )
        lay.addWidget(lbl, 1)

        self._sel_btn = QPushButton("Deselect all" if all_selected else "Select all")
        self._sel_btn.setStyleSheet(
            "QPushButton { font-size: 10px; padding: 2px 8px; border: 1px solid #555;"
            " border-radius: 3px; background: transparent; color: #777; }"
            "QPushButton:hover { background: #2a2a3a; color: #aaaaff; border-color: #7777ee; }"
        )
        self._sel_btn.clicked.connect(lambda: self.select_all_clicked.emit(self._room_name))
        lay.addWidget(self._sel_btn)

    def set_all_selected(self, v: bool):
        self._sel_btn.setText("Deselect all" if v else "Select all")


# ------------------------------------------------------------------
# Cat list card
# ------------------------------------------------------------------

class _CatCard(QFrame):
    """Compact clickable cat card shown in the list."""
    selected   = Signal(object)        # regular left-click → show detail
    ms_toggled = Signal(object, bool)  # Ctrl+click → (cat, is_now_selected)

    _NORMAL = "QFrame { background: #1c1c1c; border: 1px solid #333; border-radius: 6px; }"
    _HOVER  = "QFrame { background: #242424; border: 1px solid #555; border-radius: 6px; }"
    _ACTIVE = "QFrame { background: #1a2a1a; border: 1px solid #4caf50; border-radius: 6px; }"
    _MS_SEL = "QFrame { background: #1a1a2e; border: 2px solid #7777ee; border-radius: 6px; }"

    def __init__(self, cat, parent=None):
        super().__init__(parent)
        self._cat         = cat
        self._active      = False
        self._ms_selected = False
        self.setFixedHeight(58)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setStyleSheet(self._NORMAL)

        lay = QHBoxLayout(self)
        lay.setContentsMargins(10, 6, 10, 6)
        lay.setSpacing(8)

        g = cat.gender
        g_lbl = QLabel(_GENDER_SYMBOL.get(g, "?"))
        g_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        g_lbl.setFixedSize(28, 28)
        g_lbl.setStyleSheet(
            f"background: transparent; color: {_GENDER_COLOR.get(g, '#aaa')};"
            f" font-size: 18px; font-weight: bold;"
        )
        lay.addWidget(g_lbl)

        center = QVBoxLayout()
        center.setSpacing(2)
        self._name_lbl = QLabel(cat.name or "(unknown)")
        self._name_lbl.setStyleSheet(
            "color: #e8e8e8; font-size: 13px; font-weight: bold; background: transparent;"
        )
        center.addWidget(self._name_lbl)

        status = cat.status
        room_text = _room_display(cat.room) if cat.room and cat.room != status else status
        sub_lbl = QLabel(f"{_STATUS_ICON.get(status, '')}  {room_text}")
        sub_lbl.setStyleSheet(
            f"color: {_STATUS_COLOR.get(status, '#888')}; font-size: 11px; background: transparent;"
        )
        center.addWidget(sub_lbl)
        lay.addLayout(center, 1)

        # ── Right-side badges: mutation count + defect + disorder indicators ────
        mut_count = len(getattr(cat, "mutation_chip_items", []))
        def_count = len(getattr(cat, "defect_chip_items",   []))
        dis_count = len(getattr(cat, "disorders",           []))

        badge_parts = []
        if mut_count > 0:
            badge_parts.append((f"🧬 {mut_count}", "#80bbdd", "#0e1a22", "#2a4a5a"))
        if def_count > 0:
            badge_parts.append((f"⚡ {def_count}", "#e0a030", "#221800", "#5a3a00"))
        if dis_count > 0:
            badge_parts.append((f"⚠ {dis_count}", "#e05050", "#220e0e", "#5a1a1a"))

        if badge_parts:
            badges_row = QHBoxLayout()
            badges_row.setSpacing(3)
            badges_row.setContentsMargins(0, 0, 0, 0)
            badges_row.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight)
            for text, fg, bg, border in badge_parts:
                lbl = QLabel(text)
                lbl.setStyleSheet(
                    f"color: {fg}; font-size: 10px; background: {bg};"
                    f" border: 1px solid {border}; border-radius: 3px; padding: 1px 4px;"
                )
                lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
                badges_row.addWidget(lbl)
            badges_w = QWidget()
            badges_w.setStyleSheet("background: transparent;")
            badges_w.setLayout(badges_row)
            lay.addWidget(badges_w)

        # ── Tag badges (only when cat has tags) ──────────────────────
        cat_tags = getattr(cat, "tags", [])
        if cat_tags:
            tags_row = QHBoxLayout()
            tags_row.setSpacing(2)
            tags_row.setContentsMargins(0, 0, 0, 0)
            tags_row.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight)
            for tag in cat_tags[:3]:  # show at most 3 tags to keep card compact
                t_lbl = QLabel(f"🏷 {tag}")
                t_lbl.setStyleSheet(
                    "color: #80e0a0; font-size: 9px; background: #0e2018;"
                    " border: 1px solid #2a6040; border-radius: 3px; padding: 1px 3px;"
                )
                t_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
                tags_row.addWidget(t_lbl)
            if len(cat_tags) > 3:
                more_lbl = QLabel(f"+{len(cat_tags) - 3}")
                more_lbl.setStyleSheet(
                    "color: #60b080; font-size: 9px; background: #0a1810;"
                    " border: 1px solid #1a4030; border-radius: 3px; padding: 1px 3px;"
                )
                tags_row.addWidget(more_lbl)
            tags_w = QWidget()
            tags_w.setStyleSheet("background: transparent;")
            tags_w.setLayout(tags_row)
            lay.addWidget(tags_w)

    def update_name(self):
        """Refresh the displayed name from the underlying cat object."""
        self._name_lbl.setText(self._cat.name or "(unknown)")

    def _update_style(self):
        if self._ms_selected:
            self.setStyleSheet(self._MS_SEL)
        elif self._active:
            self.setStyleSheet(self._ACTIVE)
        else:
            self.setStyleSheet(self._NORMAL)

    def set_active(self, active: bool):
        self._active = active
        self._update_style()

    def set_ms_selected(self, selected: bool):
        self._ms_selected = selected
        self._update_style()

    def enterEvent(self, event):
        if not self._ms_selected and not self._active:
            self.setStyleSheet(self._HOVER)
        super().enterEvent(event)

    def leaveEvent(self, event):
        if not self._ms_selected and not self._active:
            self.setStyleSheet(self._NORMAL)
        super().leaveEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
                new_state = not self._ms_selected
                self.ms_toggled.emit(self._cat, new_state)
            else:
                self.selected.emit(self._cat)
        super().mousePressEvent(event)


# ------------------------------------------------------------------
# Detail panel
# ------------------------------------------------------------------

class _CatDetail(QScrollArea):
    """Right-side scrollable detail panel for a selected cat."""

    # Emitted after a successful rename so the list can be refreshed
    renamed = Signal(object)   # emits Cat
    # Emitted after a successful bank / unbank action so the list can be rebuilt
    banked  = Signal(object)   # emits Cat
    # Emitted after a successful send-cat gift so the list can be rebuilt
    sent    = Signal(object)   # emits Cat
    # Emitted after a room move
    moved   = Signal(object)   # emits Cat
    # Emitted after a cat is deleted; carries (cat, kill_count, gold_awarded)
    deleted = Signal(object, int, int)
    # Emitted after a disorder is removed from the displayed cat
    disorder_removed = Signal(object)   # emits Cat
    # Emitted after cat tags are modified
    tagged  = Signal(object)   # emits Cat

    def __init__(self, ctrl=None, parent=None):
        super().__init__(parent)
        self._ctrl = ctrl
        self._current_cat = None

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
        self._current_cat = cat

        while self._layout.count():
            item = self._layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        # ── Header ───────────────────────────────────────────────────
        header = QWidget()
        h_lay = QVBoxLayout(header)
        h_lay.setContentsMargins(0, 0, 0, 4)
        h_lay.setSpacing(4)

        # Name row: cat name only (centered)
        name_row = QHBoxLayout()
        name_row.setAlignment(Qt.AlignmentFlag.AlignCenter)

        name_lbl = QLabel(cat.name or "(unknown)")
        name_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        name_lbl.setWordWrap(True)
        name_lbl.setStyleSheet(
            "color: #f0f0f0; font-size: 20px; font-weight: bold; background: transparent;"
        )
        name_row.addWidget(name_lbl)

        name_row_w = QWidget()
        name_row_w.setStyleSheet("background: transparent;")
        name_row_w.setLayout(name_row)
        h_lay.addWidget(name_row_w)

        # Action buttons row (labeled, like the ms_bar)
        if self._ctrl is not None:
            def _action_btn(label, border, bg, fg, hover_bg="#282828"):
                b = QPushButton(label)
                b.setStyleSheet(
                    f"QPushButton {{ font-size: 11px; padding: 3px 10px;"
                    f" border: 1px solid {border}; border-radius: 4px;"
                    f" background: {bg}; color: {fg}; }}"
                    f"QPushButton:hover {{ background: {hover_bg}; color: #fff; border-color: {fg}; }}"
                    f"QPushButton:pressed {{ background: {border}44; }}"
                )
                return b

            act_row = QHBoxLayout()
            act_row.setContentsMargins(0, 2, 0, 2)
            act_row.setSpacing(5)
            act_row.setAlignment(Qt.AlignmentFlag.AlignCenter)

            # ── Rename ───────────────────────────────────────────────
            rename_btn = _action_btn("✏ Rename", "#555555", "#222222", "#aaaaaa")
            rename_btn.clicked.connect(lambda: self._do_rename(cat))
            act_row.addWidget(rename_btn)

            # ── Bank / Unbank ────────────────────────────────────────
            if cat.status == "In House":
                bank_btn = _action_btn("🏦 Bank", "#5555aa", "#1a1a3a", "#8888dd")
                bank_btn.clicked.connect(lambda: self._do_bank(cat))
                act_row.addWidget(bank_btn)
            elif cat.status == "In Bank":
                unbank_btn = _action_btn("🏠 Unbank", "#4caf50", "#1a2a1a", "#4caf50")
                unbank_btn.clicked.connect(lambda: self._do_unbank(cat))
                act_row.addWidget(unbank_btn)

            # ── Gift ─────────────────────────────────────────────────
            if cat.status in ("In House", "In Bank"):
                send_btn = _action_btn("🎁 Gift", "#aa5555", "#2a1a1a", "#dd8888")
                send_btn.clicked.connect(lambda: self._do_send_cat(cat))
                act_row.addWidget(send_btn)

            # ── Newborn-only actions ─────────────────────────────────
            if getattr(cat, "age", None) == 1:
                if cat.status == "In House":
                    move_btn = _action_btn("📍 Move Room", "#3a8a3a", "#1a2a1a", "#88cc88")
                    move_btn.clicked.connect(lambda: self._do_move_room(cat))
                    act_row.addWidget(move_btn)

                del_btn = _action_btn("🗑 Delete", "#992222", "#2a0a0a", "#cc4444")
                del_btn.clicked.connect(lambda: self._do_delete_cat(cat))
                act_row.addWidget(del_btn)

            # ── BloodFrenzy removal ──────────────────────────────────
            if "BloodFrenzy" in getattr(cat, "disorders", []):
                bf_btn = _action_btn("🩸 Remove BloodFrenzy", "#882222", "#1e0808", "#ff7777",
                                     hover_bg="#2a0e0e")
                bf_btn.clicked.connect(lambda: self._do_remove_blood_frenzy(cat))
                act_row.addWidget(bf_btn)

            act_row_w = QWidget()
            act_row_w.setStyleSheet("background: transparent;")
            act_row_w.setLayout(act_row)
            h_lay.addWidget(act_row_w)

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


        self._layout.addWidget(_section_label("📊  Stats"))
        self._layout.addWidget(self._build_stats_widget(cat))
        self._layout.addWidget(_hsep())

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
                "background: #1c1c1c; border: 1px solid #333; border-radius: 5px;"
                " padding: 4px 8px; font-size: 11px; color: #ccc;"
            )
            pers_row.addWidget(pill, 1)
        pers_w = QWidget()
        pers_w.setLayout(pers_row)
        self._layout.addWidget(pers_w)
        self._layout.addWidget(_hsep())

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

        mutation_chip_items = getattr(cat, "mutation_chip_items", [])
        defect_chip_items   = getattr(cat, "defect_chip_items",   [])

        if mutation_chip_items or defect_chip_items:
            self._layout.addWidget(_hsep())
            if mutation_chip_items:
                self._layout.addWidget(_section_label("🧬  Mutations"))
                # The tooltip for each entry starts with 2 redundant lines:
                #   "{Part} Mutation (ID N)"  ← same info as the title
                #   "{name}"                  ← same as the title
                # Strip them; keep only the stat details (line 3+).
                mut_display = [
                    (name, "\n".join(desc.split("\n")[2:]).strip() if desc else "")
                    for name, desc in mutation_chip_items
                ]
                self._layout.addWidget(
                    _ability_list(mut_display, "#131c26", "#80bbdd",
                                  desc_color="#7aaacc", use_catalog=False)
                )
            if defect_chip_items:
                self._layout.addWidget(_section_label("⚡  Defects"))
                def_display = [
                    (name, "\n".join(desc.split("\n")[2:]).strip() if desc else "")
                    for name, desc in defect_chip_items
                ]
                self._layout.addWidget(
                    _ability_list(def_display, "#261c13", "#e0a030",
                                  desc_color="#b07820", use_catalog=False)
                )

        self._layout.addWidget(_hsep())
        self._layout.addWidget(_section_label("🏷  Tags"))
        self._layout.addWidget(self._build_tags_widget(cat))
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
        self._current_cat = None
        while self._layout.count():
            item = self._layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        empty = QLabel("← Select a cat")
        empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        empty.setStyleSheet("color: #555; font-size: 16px; background: transparent;")
        self._layout.addWidget(empty)
        self._layout.addStretch()

    # ── Rename ───────────────────────────────────────────────────────

    def _do_rename(self, cat) -> None:
        new_name, ok = QInputDialog.getText(
            self, "Rename Cat", "New name:", text=cat.name or ""
        )
        if not ok:
            return
        new_name = new_name.strip()
        if not new_name:
            QMessageBox.warning(self, "Invalid Name", "The name cannot be empty.")
            return
        if new_name == cat.name:
            return
        try:
            self._ctrl.apply_rename_cat(cat, new_name)
        except Exception as exc:
            QMessageBox.critical(self, "Rename Failed", f"Could not save the new name:\n{exc}")
            return
        # Refresh the panel with the updated name
        self.show_cat(cat)
        # Signal the list to update the card label
        self.renamed.emit(cat)

    def _do_bank(self, cat) -> None:
        """Send *cat* to the cat bank."""
        reply = QMessageBox.question(
            self,
            "Send to Cat Bank",
            f"Send <b>{cat.name}</b> to the cat bank?<br><br>"
            "The cat will be removed from the house until you move it back.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        try:
            self._ctrl.apply_bank_cat(cat)
        except Exception as exc:
            QMessageBox.critical(self, "Error", f"Could not bank cat:\n{exc}")
            return
        self.show_cat(cat)
        self.banked.emit(cat)

    def _do_unbank(self, cat) -> None:
        """Move *cat* from the cat bank back to the house."""
        reply = QMessageBox.question(
            self,
            "Move to House",
            f"Move <b>{cat.name}</b> back to the house?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        try:
            self._ctrl.apply_unbank_cat(cat)
        except Exception as exc:
            QMessageBox.critical(self, "Error", f"Could not unbank cat:\n{exc}")
            return
        self.show_cat(cat)
        self.banked.emit(cat)

    def _do_send_cat(self, cat) -> None:
        """Send *cat* as a gift to the partner via the remote PostgreSQL cat_trade table."""
        try:
            ctx = self._ctrl.get_gift_context()
        except Exception as exc:
            QMessageBox.critical(self, "Error", f"Could not determine gift context:\n{exc}")
            return

        if not ctx.get("is_known_user"):
            QMessageBox.warning(
                self, "Cannot Send Gift",
                "Your save file's Steam ID was not recognised.\n"
                "Gift features require a known user pair configured in version.py."
            )
            return

        reply = QMessageBox.question(
            self,
            "🎁 Send Cat",
            f"Send <b>{cat.name}</b> to <b>{ctx['recipient_name']}</b>?<br><br>"
            "The cat will be removed from your save.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        try:
            self._ctrl.apply_send_cat(cat)
        except Exception as exc:
            QMessageBox.critical(self, "Send Failed", f"Could not send cat:\n{exc}")
            return

        self.show_cat(cat)
        self.sent.emit(cat)

    def _do_move_room(self, cat) -> None:
        """Show a dialog to pick a new room for *cat*."""
        rooms = self._ctrl.get_available_rooms() if self._ctrl else []
        if not rooms:
            QMessageBox.information(self, "No Rooms", "No rooms found in the current house state.")
            return
        from PySide6.QtWidgets import QInputDialog
        display_names = [_room_display(r) for r in rooms]
        dlg = QInputDialog(self)
        dlg.setWindowTitle("Move to Room")
        dlg.setLabelText(f"Choose destination room for {cat.name}:")
        dlg.setComboBoxItems(display_names)
        dlg.setComboBoxEditable(False)
        dlg.setMinimumWidth(360)
        ok = dlg.exec()
        display = dlg.textValue()
        if not ok or not display:
            return
        # Map display name back to internal room key
        room = rooms[display_names.index(display)] if display in display_names else display
        if room == cat.room:
            return
        try:
            self._ctrl.apply_move_cat_room(cat, room)
        except Exception as exc:
            QMessageBox.critical(self, "Move Failed", f"Could not move cat:\n{exc}")
            return
        self.show_cat(cat)
        self.moved.emit(cat)

    def _do_remove_blood_frenzy(self, cat) -> None:
        """Remove the BloodFrenzy disorder from *cat* after confirmation."""
        reply = QMessageBox.question(
            self, "🩸 Remove BloodFrenzy",
            f"<b>Remove BloodFrenzy from {cat.name}?</b><br><br>"
            f"This will permanently modify the cat's save data.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        try:
            n_modified, _ = self._ctrl.apply_remove_disorder_bulk("BloodFrenzy", cats=[cat])
        except Exception as exc:
            QMessageBox.critical(self, "Error", f"Could not remove BloodFrenzy:\n{exc}")
            return
        if n_modified:
            self.disorder_removed.emit(cat)
        else:
            QMessageBox.warning(self, "Not Found",
                                "BloodFrenzy was not found in the cat's blob.")

    def _do_delete_cat(self, cat) -> None:
        """Permanently delete *cat* after confirmation."""
        kills_now   = getattr(self._ctrl, "newborn_kill_count", 0) if self._ctrl else 0
        next_reward = 10 - (kills_now % 10)
        reply = QMessageBox.question(
            self, "🗑 Delete Newborn",
            f"<b>Permanently delete {cat.name}?</b><br><br>"
            f"This cannot be undone.<br>"
            f"Kill counter: <b>{kills_now}</b> — "
            f"next 🪙 25 gold reward in <b>{next_reward}</b> more kill(s).",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        try:
            new_count, gold = self._ctrl.apply_delete_cat(cat)
        except Exception as exc:
            QMessageBox.critical(self, "Delete Failed", f"Could not delete cat:\n{exc}")
            return
        self.deleted.emit(cat, new_count, gold)

    # ── Tag management ────────────────────────────────────────────────

    def _build_tags_widget(self, cat) -> QWidget:
        """Build a widget showing current tags with remove buttons + an Add button."""
        w = QWidget()
        w.setStyleSheet("background: transparent;")
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(4)

        tags = list(getattr(cat, "tags", []))

        if tags:
            tags_row = QHBoxLayout()
            tags_row.setSpacing(4)
            tags_row.setContentsMargins(0, 0, 0, 0)
            tags_row.setAlignment(Qt.AlignmentFlag.AlignLeft)
            for tag in tags:
                pill = QWidget()
                pill.setStyleSheet(
                    "background: #0e2018; border: 1px solid #2a6040; border-radius: 4px;"
                )
                pill_lay = QHBoxLayout(pill)
                pill_lay.setContentsMargins(5, 2, 2, 2)
                pill_lay.setSpacing(3)
                tag_lbl = QLabel(f"🏷 {tag}")
                tag_lbl.setStyleSheet(
                    "color: #80e0a0; font-size: 11px; background: transparent; border: none;"
                )
                pill_lay.addWidget(tag_lbl)
                rm_btn = QPushButton("×")
                rm_btn.setFixedSize(16, 16)
                rm_btn.setStyleSheet(
                    "QPushButton { background: transparent; border: none; color: #60a070;"
                    " font-size: 12px; font-weight: bold; padding: 0; }"
                    "QPushButton:hover { color: #ff6060; }"
                )
                rm_btn.clicked.connect(lambda _=False, t=tag, c=cat: self._do_remove_tag(c, t))
                pill_lay.addWidget(rm_btn)
                tags_row.addWidget(pill)
            tags_w = QWidget()
            tags_w.setStyleSheet("background: transparent;")
            tags_w.setLayout(tags_row)
            lay.addWidget(tags_w)
        else:
            no_lbl = QLabel("No tags")
            no_lbl.setStyleSheet("color: #555; font-size: 11px; background: transparent;")
            lay.addWidget(no_lbl)

        add_btn = QPushButton("＋ Add Tag")
        add_btn.setStyleSheet(
            "QPushButton { font-size: 10px; padding: 2px 8px; border: 1px solid #2a6040;"
            " border-radius: 4px; background: #0e2018; color: #60b080; }"
            "QPushButton:hover { background: #162a20; color: #80e0a0; }"
        )
        add_btn.clicked.connect(lambda: self._do_add_tag(cat))
        lay.addWidget(add_btn)
        return w

    def _do_add_tag(self, cat) -> None:
        """Open a dialog to add a new tag to *cat*."""
        if self._ctrl is None:
            return
        # Build list of existing tags for suggestions
        existing_all = self._ctrl.get_all_cat_tags()
        current      = list(getattr(cat, "tags", []))
        suggestions  = [t for t in existing_all if t not in current]

        from PySide6.QtWidgets import QInputDialog
        dlg = QInputDialog(self)
        dlg.setWindowTitle("Add Tag")
        dlg.setLabelText(f"Tag for {cat.name}:")
        dlg.setComboBoxEditable(True)
        dlg.setComboBoxItems(suggestions)
        dlg.setMinimumWidth(300)
        if not dlg.exec():
            return
        tag = dlg.textValue().strip()
        if not tag:
            return
        try:
            self._ctrl.apply_add_cat_tag(cat, tag)
        except Exception as exc:
            QMessageBox.critical(self, "Error", str(exc))
            return
        self.show_cat(cat)
        self.tagged.emit(cat)

    def _do_remove_tag(self, cat, tag: str) -> None:
        """Remove *tag* from *cat* after confirmation."""
        if self._ctrl is None:
            return
        try:
            self._ctrl.apply_remove_cat_tag(cat, tag)
        except Exception as exc:
            QMessageBox.critical(self, "Error", str(exc))
            return
        self.show_cat(cat)
        self.tagged.emit(cat)

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
# Query-builder: single filter row
# ------------------------------------------------------------------

class _FilterBlockRow(QFrame):
    """One condition row: [field type] [operator] [value] [× remove]."""

    removed = Signal(object)   # emits self
    changed = Signal()

    _COMBO_SS = (
        "QComboBox { font-size: 11px; padding: 2px 5px; border: 1px solid #3a3a4a;"
        " border-radius: 3px; background: #14141e; color: #ccc; min-height: 20px; }"
        "QComboBox:hover { border-color: #5555aa; }"
        "QComboBox::drop-down { border: none; width: 16px; }"
        "QComboBox QAbstractItemView { background: #1a1a2a; color: #ccc;"
        " border: 1px solid #3a3a5a; selection-background-color: #2a2a4a; }"
    )
    _INPUT_SS = (
        "QLineEdit { font-size: 11px; padding: 2px 5px; border: 1px solid #3a3a4a;"
        " border-radius: 3px; background: #14141e; color: #ccc; }"
        "QLineEdit:focus { border-color: #5555aa; }"
    )
    _SPIN_SS = (
        "QSpinBox { font-size: 11px; padding: 2px 4px; border: 1px solid #3a3a4a;"
        " border-radius: 3px; background: #14141e; color: #ccc; }"
        "QSpinBox::up-button, QSpinBox::down-button { width: 14px; }"
    )

    def __init__(self, block=None, parent=None):
        super().__init__(parent)
        self.setStyleSheet(
            "QFrame { background: #14141e; border: 1px solid #2a2a3a; border-radius: 4px; }"
        )
        lay = QHBoxLayout(self)
        lay.setContentsMargins(6, 4, 4, 4)
        lay.setSpacing(4)

        # Field-type combo
        self._type_cb = QComboBox()
        self._type_cb.setStyleSheet(self._COMBO_SS)
        self._type_cb.setMinimumWidth(148)
        for ft_val, ft_label in _FILTER_TYPE_LABELS.items():
            self._type_cb.addItem(ft_label, ft_val)

        # Operator combo
        self._op_cb = QComboBox()
        self._op_cb.setStyleSheet(self._COMBO_SS)
        self._op_cb.setMinimumWidth(128)

        # Value widget holder (swapped dynamically)
        self._val_holder = QWidget()
        self._val_holder.setStyleSheet("background: transparent;")
        self._val_holder.setMinimumWidth(120)
        self._val_lay = QHBoxLayout(self._val_holder)
        self._val_lay.setContentsMargins(0, 0, 0, 0)
        self._val_lay.setSpacing(0)
        self._val_w: QWidget | None = None

        # Remove button
        rm = QPushButton("×")
        rm.setFixedSize(20, 20)
        rm.setStyleSheet(
            "QPushButton { background: #1e0e0e; border: 1px solid #553333;"
            " border-radius: 3px; color: #cc5555; font-size: 13px;"
            " font-weight: bold; padding: 0; }"
            "QPushButton:hover { background: #2a1010; color: #ff7777; }"
        )
        rm.clicked.connect(lambda: self.removed.emit(self))

        lay.addWidget(self._type_cb)
        lay.addWidget(self._op_cb)
        lay.addWidget(self._val_holder, 1)
        lay.addWidget(rm)

        self._type_cb.currentIndexChanged.connect(self._on_type_changed)
        self._op_cb.currentIndexChanged.connect(self._on_op_changed)

        if block is not None:
            self._load_block(block)
        else:
            self._on_type_changed()

    # ── Loading ──────────────────────────────────────────────────────

    def _load_block(self, block) -> None:
        idx = self._type_cb.findData(block.filter_type)
        if idx >= 0:
            self._type_cb.blockSignals(True)
            self._type_cb.setCurrentIndex(idx)
            self._type_cb.blockSignals(False)
        self._rebuild_op_combo(block.filter_type)
        idx = self._op_cb.findData(block.operator)
        if idx >= 0:
            self._op_cb.blockSignals(True)
            self._op_cb.setCurrentIndex(idx)
            self._op_cb.blockSignals(False)
        self._rebuild_val_widget(block.filter_type, block.operator, block.value)

    # ── Slots ────────────────────────────────────────────────────────

    def _on_type_changed(self) -> None:
        ft = self._type_cb.currentData()
        self._rebuild_op_combo(ft)
        self._rebuild_val_widget(ft, self._op_cb.currentData())
        self.changed.emit()

    def _on_op_changed(self) -> None:
        ft = self._type_cb.currentData()
        op = self._op_cb.currentData()
        self._rebuild_val_widget(ft, op)
        self.changed.emit()

    # ── Rebuilders ───────────────────────────────────────────────────

    def _rebuild_op_combo(self, ft: str) -> None:
        from utils.cat_query_filters import FilterType, ALLOWED_OPERATORS
        self._op_cb.blockSignals(True)
        self._op_cb.clear()
        ft_enum = next((e for e in FilterType if e.value == ft), None)
        for op in (ALLOWED_OPERATORS.get(ft_enum) or ()):
            self._op_cb.addItem(_OPERATOR_LABELS.get(op.value, op.value), op.value)
        self._op_cb.blockSignals(False)

    def _rebuild_val_widget(self, ft: str, op: str, initial=None) -> None:
        # Tear down previous widget
        if self._val_w is not None:
            self._val_lay.removeWidget(self._val_w)
            self._val_w.deleteLater()
            self._val_w = None

        if op in _NO_VALUE_OPERATORS:
            lbl = QLabel("—")
            lbl.setStyleSheet("color: #444; font-size: 11px; background: transparent;")
            self._val_lay.addWidget(lbl)
            self._val_w = lbl
            return

        # Room + EQ/NE → dropdown of display names
        if ft == "room" and op in ("eq", "ne"):
            w = QComboBox()
            w.setStyleSheet(self._COMBO_SS)
            for display_name in ROOM_DISPLAY_NAMES.values():
                w.addItem(display_name, display_name)
            if initial is not None:
                i = w.findData(str(initial))
                if i >= 0:
                    w.setCurrentIndex(i)
            w.currentIndexChanged.connect(self.changed.emit)
            self._val_lay.addWidget(w)
            self._val_w = w
            return

        if ft in _STRING_FIELD_CHOICES:
            w = QComboBox()
            w.setStyleSheet(self._COMBO_SS)
            for choice in _STRING_FIELD_CHOICES[ft]:
                w.addItem(choice, choice)
            if initial is not None:
                i = w.findData(str(initial))
                if i >= 0:
                    w.setCurrentIndex(i)
            w.currentIndexChanged.connect(self.changed.emit)

        elif ft in ("mutation_count", "defects_count"):
            w = QSpinBox()
            w.setStyleSheet(self._SPIN_SS)
            w.setRange(0, 99)
            if initial is not None:
                try:
                    w.setValue(int(initial))
                except (TypeError, ValueError):
                    pass
            w.valueChanged.connect(self.changed.emit)

        else:
            w = QLineEdit()
            w.setStyleSheet(self._INPUT_SS)
            if op in ("any_of", "none_of"):
                w.setPlaceholderText("val1, val2, …")
                if isinstance(initial, list):
                    w.setText(", ".join(str(v) for v in initial))
                elif initial:
                    w.setText(str(initial))
            else:
                w.setPlaceholderText("value…")
                if initial is not None:
                    w.setText(str(initial))
            w.textChanged.connect(self.changed.emit)

        self._val_lay.addWidget(w)
        self._val_w = w

    # ── Public ───────────────────────────────────────────────────────

    def to_block(self):
        """Return a FilterBlock for the current row, or None if invalid."""
        from utils.cat_query_filters import FilterBlock
        ft = self._type_cb.currentData()
        op = self._op_cb.currentData()
        if not ft or not op:
            return None
        value = None
        if op not in _NO_VALUE_OPERATORS and self._val_w is not None:
            w = self._val_w
            if isinstance(w, QComboBox):
                value = w.currentData()
            elif isinstance(w, QSpinBox):
                value = w.value()
            elif isinstance(w, QLineEdit):
                text = w.text().strip()
                if op in ("any_of", "none_of"):
                    value = [v.strip() for v in text.split(",") if v.strip()]
                else:
                    value = text if text else None
        return FilterBlock(filter_type=ft, operator=op, value=value)


# ------------------------------------------------------------------
# Query-builder: collapsible panel (Newborns tab)
# ------------------------------------------------------------------

class _NewbornQueryBar(QWidget):
    """Collapsible advanced query-builder shown below the Newborns sub-filter bar."""

    changed = Signal()

    def __init__(self, presets_path: str, parent=None):
        super().__init__(parent)
        self._presets_path = presets_path
        self._rows: list[_FilterBlockRow] = []
        self._logical_op = "AND"

        self.setStyleSheet(
            "QWidget { background: #0c0c18; border-bottom: 1px solid #1a1a3a; }"
        )

        root_lay = QVBoxLayout(self)
        root_lay.setContentsMargins(0, 0, 0, 0)
        root_lay.setSpacing(0)

        # ── Header (always visible) ────────────────────────────────────
        hdr = QWidget()
        hdr.setStyleSheet(
            "QWidget { background: #0c0c18; border-bottom: 1px solid #181828; }"
        )
        hdr_lay = QHBoxLayout(hdr)
        hdr_lay.setContentsMargins(10, 4, 10, 4)
        hdr_lay.setSpacing(8)

        self._toggle_btn = QPushButton("🔍 Advanced Filter  ▾")
        self._toggle_btn.setCheckable(True)
        self._toggle_btn.setStyleSheet(
            "QPushButton { font-size: 11px; padding: 2px 10px;"
            " border: 1px solid #2a2a5a; border-radius: 4px;"
            " background: transparent; color: #6666aa; }"
            "QPushButton:checked { color: #aaaaff; border-color: #5555aa;"
            " font-weight: bold; }"
            "QPushButton:hover { background: #0e0e2a; color: #8888cc; }"
        )
        self._toggle_btn.clicked.connect(self._on_toggle)
        hdr_lay.addWidget(self._toggle_btn)

        self._status_lbl = QLabel("")
        self._status_lbl.setStyleSheet(
            "color: #5555aa; font-size: 10px; background: transparent;"
        )
        hdr_lay.addWidget(self._status_lbl)
        hdr_lay.addStretch()

        self._clear_btn = QPushButton("✕ Clear all")
        self._clear_btn.setStyleSheet(
            "QPushButton { font-size: 10px; padding: 2px 8px;"
            " border: 1px solid #3a2a3a; border-radius: 3px;"
            " background: transparent; color: #886688; }"
            "QPushButton:hover { background: #1e0e1e; color: #cc88cc; }"
        )
        self._clear_btn.clicked.connect(self._clear_all)
        self._clear_btn.hide()
        hdr_lay.addWidget(self._clear_btn)

        root_lay.addWidget(hdr)

        # ── Body (collapsible) ─────────────────────────────────────────
        self._body = QWidget()
        self._body.setStyleSheet("QWidget { background: #0c0c18; }")
        body_lay = QVBoxLayout(self._body)
        body_lay.setContentsMargins(10, 6, 10, 8)
        body_lay.setSpacing(5)

        # Logic-op row
        op_row = QHBoxLayout()
        op_row.setContentsMargins(0, 0, 0, 2)
        op_row.setSpacing(5)

        match_lbl = QLabel("Match:")
        match_lbl.setStyleSheet(
            "color: #666; font-size: 11px; background: transparent;"
        )
        op_row.addWidget(match_lbl)

        _and_act = (
            "QPushButton { font-size: 11px; padding: 1px 10px;"
            " border: 1px solid #4444aa; border-radius: 3px;"
            " background: #14143a; color: #8888ee; font-weight: bold; }"
        )
        _and_norm = (
            "QPushButton { font-size: 11px; padding: 1px 10px;"
            " border: 1px solid #333; border-radius: 3px;"
            " background: transparent; color: #666; }"
            "QPushButton:hover { background: #0e0e2a; color: #9999cc; }"
        )
        _or_act = (
            "QPushButton { font-size: 11px; padding: 1px 10px;"
            " border: 1px solid #aa6633; border-radius: 3px;"
            " background: #2a1a0e; color: #ee9966; font-weight: bold; }"
        )
        _or_norm = (
            "QPushButton { font-size: 11px; padding: 1px 10px;"
            " border: 1px solid #333; border-radius: 3px;"
            " background: transparent; color: #666; }"
            "QPushButton:hover { background: #1a0e0e; color: #cc9966; }"
        )
        self._and_act_ss = _and_act
        self._and_norm_ss = _and_norm
        self._or_act_ss = _or_act
        self._or_norm_ss = _or_norm

        self._and_btn = QPushButton("ALL (AND)")
        self._and_btn.setStyleSheet(_and_act)
        self._or_btn = QPushButton("ANY (OR)")
        self._or_btn.setStyleSheet(_or_norm)
        self._and_btn.clicked.connect(lambda: self._set_logical_op("AND"))
        self._or_btn.clicked.connect(lambda: self._set_logical_op("OR"))
        op_row.addWidget(self._and_btn)
        op_row.addWidget(self._or_btn)
        op_row.addStretch()

        add_cond_btn = QPushButton("＋ Add condition")
        add_cond_btn.setStyleSheet(
            "QPushButton { font-size: 11px; padding: 1px 10px;"
            " border: 1px solid #2a4a2a; border-radius: 3px;"
            " background: transparent; color: #558855; }"
            "QPushButton:hover { background: #0a180a; color: #88cc88; }"
        )
        add_cond_btn.clicked.connect(lambda: self._add_row())
        op_row.addWidget(add_cond_btn)
        body_lay.addLayout(op_row)

        # Filter rows container
        self._rows_w = QWidget()
        self._rows_w.setStyleSheet("background: transparent;")
        self._rows_lay = QVBoxLayout(self._rows_w)
        self._rows_lay.setContentsMargins(0, 0, 0, 0)
        self._rows_lay.setSpacing(3)
        body_lay.addWidget(self._rows_w)

        # Preset bar
        pre_row = QHBoxLayout()
        pre_row.setContentsMargins(0, 4, 0, 0)
        pre_row.setSpacing(5)

        pre_lbl = QLabel("Presets:")
        pre_lbl.setStyleSheet("color: #555; font-size: 10px; background: transparent;")
        pre_row.addWidget(pre_lbl)

        self._preset_name_edit = QLineEdit()
        self._preset_name_edit.setFixedWidth(110)
        self._preset_name_edit.setPlaceholderText("name…")
        self._preset_name_edit.setStyleSheet(
            "QLineEdit { font-size: 10px; padding: 2px 5px;"
            " border: 1px solid #2a3a2a; border-radius: 3px;"
            " background: #0a140a; color: #88aa88; }"
        )
        pre_row.addWidget(self._preset_name_edit)

        save_p_btn = QPushButton("💾")
        save_p_btn.setFixedSize(26, 22)
        save_p_btn.setToolTip("Save current filter as a preset")
        save_p_btn.setStyleSheet(
            "QPushButton { font-size: 12px; padding: 0;"
            " border: 1px solid #2a4a2a; border-radius: 3px;"
            " background: #0a180a; color: #55aa55; }"
            "QPushButton:hover { background: #0e1e0e; color: #88cc88; }"
        )
        save_p_btn.clicked.connect(self._on_save_preset)
        pre_row.addWidget(save_p_btn)

        self._preset_cb = QComboBox()
        self._preset_cb.setMinimumWidth(110)
        self._preset_cb.setStyleSheet(
            "QComboBox { font-size: 10px; padding: 2px 5px;"
            " border: 1px solid #2a2a4a; border-radius: 3px;"
            " background: #0a0a18; color: #8888aa; }"
            "QComboBox QAbstractItemView { background: #14141e; color: #aaa;"
            " border: 1px solid #3a3a5a; }"
        )
        pre_row.addWidget(self._preset_cb)

        load_p_btn = QPushButton("📂")
        load_p_btn.setFixedSize(26, 22)
        load_p_btn.setToolTip("Load selected preset")
        load_p_btn.setStyleSheet(
            "QPushButton { font-size: 12px; padding: 0;"
            " border: 1px solid #2a3a4a; border-radius: 3px;"
            " background: #0a0e18; color: #5577aa; }"
            "QPushButton:hover { background: #0e1420; color: #88aadd; }"
        )
        load_p_btn.clicked.connect(self._on_load_preset)
        pre_row.addWidget(load_p_btn)

        del_p_btn = QPushButton("🗑")
        del_p_btn.setFixedSize(26, 22)
        del_p_btn.setToolTip("Delete selected preset")
        del_p_btn.setStyleSheet(
            "QPushButton { font-size: 12px; padding: 0;"
            " border: 1px solid #3a2222; border-radius: 3px;"
            " background: #140a0a; color: #aa4444; }"
            "QPushButton:hover { background: #1e0e0e; color: #dd6666; }"
        )
        del_p_btn.clicked.connect(self._on_delete_preset)
        pre_row.addWidget(del_p_btn)

        pre_row.addStretch()
        body_lay.addLayout(pre_row)

        self._body.hide()
        root_lay.addWidget(self._body)

        self._refresh_presets_combo()

    # ── Public ────────────────────────────────────────────────────────

    def get_filter_group(self):
        """Return the active FilterGroup, or None when no conditions are defined."""
        from utils.cat_query_filters import FilterGroup
        blocks = [r.to_block() for r in self._rows]
        blocks = [b for b in blocks if b is not None]
        if not blocks:
            return None
        return FilterGroup(logical_op=self._logical_op, children=blocks)

    # ── Private ───────────────────────────────────────────────────────

    def _on_toggle(self, checked: bool) -> None:
        if checked:
            self._body.show()
            self._toggle_btn.setText("🔍 Advanced Filter  ▴")
        else:
            self._body.hide()
            self._toggle_btn.setText("🔍 Advanced Filter  ▾")

    def _set_logical_op(self, op: str) -> None:
        self._logical_op = op
        self._and_btn.setStyleSheet(
            self._and_act_ss if op == "AND" else self._and_norm_ss
        )
        self._or_btn.setStyleSheet(
            self._or_act_ss if op == "OR" else self._or_norm_ss
        )
        self.changed.emit()

    def _add_row(self, block=None) -> None:
        row = _FilterBlockRow(block)
        row.removed.connect(self._remove_row)
        row.changed.connect(self._on_rows_changed)
        self._rows.append(row)
        self._rows_lay.addWidget(row)
        self._update_status()
        self.changed.emit()

    def _remove_row(self, row) -> None:
        if row in self._rows:
            self._rows.remove(row)
        self._rows_lay.removeWidget(row)
        row.deleteLater()
        self._update_status()
        self.changed.emit()

    def _on_rows_changed(self) -> None:
        self._update_status()
        self.changed.emit()

    def _clear_all(self) -> None:
        for row in list(self._rows):
            self._rows_lay.removeWidget(row)
            row.deleteLater()
        self._rows.clear()
        self._update_status()
        self.changed.emit()

    def _update_status(self) -> None:
        n = len(self._rows)
        if n == 0:
            self._status_lbl.setText("")
            self._clear_btn.hide()
        else:
            s = "s" if n != 1 else ""
            self._status_lbl.setText(f"● {n} condition{s} active")
            self._clear_btn.show()

    def _refresh_presets_combo(self) -> None:
        from utils.cat_query_filters import list_presets
        self._preset_cb.blockSignals(True)
        self._preset_cb.clear()
        if self._presets_path:
            try:
                for name in list_presets(self._presets_path):
                    self._preset_cb.addItem(name, name)
            except Exception:
                pass
        self._preset_cb.blockSignals(False)

    def _on_save_preset(self) -> None:
        from utils.cat_query_filters import save_preset, FilterGroup
        name = self._preset_name_edit.text().strip()
        if not name:
            QMessageBox.warning(self, "Save Preset", "Please enter a preset name.")
            return
        if not self._presets_path:
            QMessageBox.warning(self, "Save Preset", "No save folder detected.")
            return
        group = self.get_filter_group() or FilterGroup(logical_op=self._logical_op)
        try:
            save_preset(name, group, self._presets_path)
        except Exception as exc:
            QMessageBox.critical(self, "Save Preset", f"Could not save:\n{exc}")
            return
        self._refresh_presets_combo()
        idx = self._preset_cb.findData(name)
        if idx >= 0:
            self._preset_cb.setCurrentIndex(idx)

    def _on_load_preset(self) -> None:
        from utils.cat_query_filters import load_preset, FilterBlock
        name = self._preset_cb.currentData()
        if not name or not self._presets_path:
            return
        try:
            group = load_preset(name, self._presets_path)
        except Exception as exc:
            QMessageBox.critical(self, "Load Preset", f"Could not load:\n{exc}")
            return
        self._clear_all()
        self._set_logical_op(group.logical_op)
        for child in group.children:
            if isinstance(child, FilterBlock):
                self._add_row(child)
        # Auto-expand if collapsed
        if not self._toggle_btn.isChecked():
            self._toggle_btn.setChecked(True)
            self._on_toggle(True)
        self._preset_name_edit.setText(name)

    def _on_delete_preset(self) -> None:
        from utils.cat_query_filters import delete_preset
        name = self._preset_cb.currentData()
        if not name or not self._presets_path:
            return
        reply = QMessageBox.question(
            self, "Delete Preset",
            f"Delete preset <b>{name}</b>?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        try:
            delete_preset(name, self._presets_path)
        except Exception as exc:
            QMessageBox.critical(self, "Delete Preset", f"Could not delete:\n{exc}")
            return
        self._refresh_presets_combo()


# ------------------------------------------------------------------
# Main Cat Manager window
# ------------------------------------------------------------------

class CatManagerWindow(QWidget):
    """Standalone window showing all cats parsed from the save file."""

    def __init__(self, cats: list, ctrl=None, parent=None):
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
        self._ctrl = ctrl
        self._active_card: _CatCard | None = None
        self._ms_selected: set = set()   # set of Cat objects currently multi-selected

        # ── Filter bar ───────────────────────────────────────────────
        filter_bar = QWidget()
        filter_bar.setStyleSheet("QWidget { background: #171717; border-bottom: 1px solid #333; }")
        fb_lay = QHBoxLayout(filter_bar)
        fb_lay.setContentsMargins(10, 6, 10, 6)
        fb_lay.setSpacing(6)

        self._filter = "house"
        self._sub_filter       = "all"   # mutation/disorder sub-filter for the "newborns" tab
        self._gender_filter    = "all"   # gender sub-filter for the "newborns" tab
        self._sexuality_filter = "all"   # sexuality sub-filter for the "newborns" tab
        self._tag_filter       = "all"   # tag filter for the "bank" tab
        _btn_style_active = (
            "QPushButton { font-size: 12px; padding: 3px 12px; border: 1px solid #4caf50;"
            " border-radius: 4px; background: #1a2d1a; color: #4caf50; font-weight: bold; }"
        )
        _btn_style = (
            "QPushButton { font-size: 12px; padding: 3px 12px; border: 1px solid #444;"
            " border-radius: 4px; background: #1e1e1e; color: #aaa; }"
            "QPushButton:hover { background: #282828; color: #ccc; }"
        )
        _newborn_active = (
            "QPushButton { font-size: 12px; padding: 3px 12px; border: 1px solid #e0c060;"
            " border-radius: 4px; background: #2a2510; color: #e0c060; font-weight: bold; }"
        )
        _newborn_normal = (
            "QPushButton { font-size: 12px; padding: 3px 12px; border: 1px solid #444;"
            " border-radius: 4px; background: #1e1e1e; color: #aaa; }"
            "QPushButton:hover { background: #282820; color: #e0c060; }"
        )
        self._filter_btns: dict[str, QPushButton] = {}
        self._filter_btn_active_style = _btn_style_active
        self._filter_btn_normal_style = _btn_style

        # Only "In House", "Adventure", "In Bank" and "Newborns" — no "All"
        for key, label in [("house", "🏠 In House"), ("adventure", "⚔️ Adventure"),
                            ("bank", "🏦 In Bank"), ("newborns", "🍼 Newborns")]:
            btn = QPushButton(label)
            if key == "newborns":
                btn.setStyleSheet(_newborn_active if key == self._filter else _newborn_normal)
                btn.setProperty("newborn_btn", True)
            else:
                btn.setStyleSheet(_btn_style_active if key == self._filter else _btn_style)
            btn.clicked.connect(lambda _=False, k=key: self._set_filter(k))
            self._filter_btns[key] = btn
            fb_lay.addWidget(btn)

        self._count_lbl = QLabel()
        self._count_lbl.setStyleSheet("color: #666; font-size: 12px; background: transparent;")
        fb_lay.addWidget(self._count_lbl)
        fb_lay.addStretch()

        # ── Receive cats button ──────────────────────────────────────
        _recv_style = (
            "QPushButton { font-size: 12px; padding: 3px 12px; border: 1px solid #884444;"
            " border-radius: 4px; background: #2a1a1a; color: #cc8888; }"
            "QPushButton:hover { background: #3a2020; color: #ffaaaa; }"
        )
        recv_btn = QPushButton("📬 Receive Cats")
        recv_btn.setStyleSheet(_recv_style)
        recv_btn.clicked.connect(self._on_receive_cats)
        fb_lay.addWidget(recv_btn)

        # ── Remove BloodFrenzy button ────────────────────────────────
        _bf_style = (
            "QPushButton { font-size: 12px; padding: 3px 12px; border: 1px solid #aa4444;"
            " border-radius: 4px; background: #2a1010; color: #ff7777; }"
            "QPushButton:hover { background: #3a1515; color: #ffaaaa; }"
        )
        bf_btn = QPushButton("🩸 Remove BloodFrenzy")
        bf_btn.setStyleSheet(_bf_style)
        bf_btn.setToolTip("Remove the BloodFrenzy disorder from all In-House and Adventure cats")
        bf_btn.clicked.connect(self._on_remove_blood_frenzy)
        fb_lay.addWidget(bf_btn)

        # ── Newborns sub-filter bar (hidden unless "newborns" tab active) ──
        self._sub_filter_bar = QWidget()
        self._sub_filter_bar.setStyleSheet(
            "QWidget { background: #131308; border-bottom: 1px solid #3a3800; }"
        )
        sfb_root = QVBoxLayout(self._sub_filter_bar)
        sfb_root.setContentsMargins(10, 4, 10, 4)
        sfb_root.setSpacing(3)

        # ── Row 1: mutation / disorder filter ────────────────────────
        sfb_lay = QHBoxLayout()
        sfb_lay.setContentsMargins(0, 0, 0, 0)
        sfb_lay.setSpacing(6)

        sfb_lbl = QLabel("Filter:")
        sfb_lbl.setStyleSheet("color: #888; font-size: 11px; background: transparent;")
        sfb_lay.addWidget(sfb_lbl)

        _sf_active = (
            "QPushButton { font-size: 11px; padding: 2px 10px; border: 1px solid #e0c060;"
            " border-radius: 4px; background: #2a2510; color: #e0c060; font-weight: bold; }"
        )
        _sf_normal = (
            "QPushButton { font-size: 11px; padding: 2px 10px; border: 1px solid #333;"
            " border-radius: 4px; background: #1a1a14; color: #999; }"
            "QPushButton:hover { background: #222218; color: #e0c060; }"
        )
        self._sub_filter_btn_active_style = _sf_active
        self._sub_filter_btn_normal_style = _sf_normal
        self._sub_filter_btns: dict[str, QPushButton] = {}

        for sf_key, sf_label in [
            ("all",      "🐱 All"),
            ("defects",  "⚠ Has Disorders"),
            ("lt8",      "🧬 < 8 Mutations"),
            ("eq8",      "🧬 8 Mutations"),
            ("eq9",      "🧬 9 Mutations"),
            ("eq10",     "🧬 10 Mutations"),
        ]:
            sb = QPushButton(sf_label)
            sb.setStyleSheet(_sf_active if sf_key == "all" else _sf_normal)
            sb.clicked.connect(lambda _=False, k=sf_key: self._set_sub_filter(k))
            self._sub_filter_btns[sf_key] = sb
            sfb_lay.addWidget(sb)

        sfb_lay.addStretch()

        self._kill_count_lbl = QLabel("")
        self._kill_count_lbl.setStyleSheet(
            "color: #cc6666; font-size: 11px; background: transparent;"
        )
        sfb_lay.addWidget(self._kill_count_lbl)
        sfb_root.addLayout(sfb_lay)

        # ── Row 2: gender filter ──────────────────────────────────────
        sgf_lay = QHBoxLayout()
        sgf_lay.setContentsMargins(0, 0, 0, 0)
        sgf_lay.setSpacing(6)

        sgf_lbl = QLabel("Gender:")
        sgf_lbl.setStyleSheet("color: #888; font-size: 11px; background: transparent;")
        sgf_lay.addWidget(sgf_lbl)

        _gf_active_all = (
            "QPushButton { font-size: 11px; padding: 2px 10px; border: 1px solid #e0c060;"
            " border-radius: 4px; background: #2a2510; color: #e0c060; font-weight: bold; }"
        )
        _gf_active_m = (
            "QPushButton { font-size: 11px; padding: 2px 10px; border: 1px solid #5b9cf6;"
            " border-radius: 4px; background: #101828; color: #5b9cf6; font-weight: bold; }"
        )
        _gf_active_f = (
            "QPushButton { font-size: 11px; padding: 2px 10px; border: 1px solid #f47abf;"
            " border-radius: 4px; background: #28101e; color: #f47abf; font-weight: bold; }"
        )
        _gf_active_d = (
            "QPushButton { font-size: 11px; padding: 2px 10px; border: 1px solid #aaaaaa;"
            " border-radius: 4px; background: #1e1e1e; color: #cccccc; font-weight: bold; }"
        )
        _gf_normal = (
            "QPushButton { font-size: 11px; padding: 2px 10px; border: 1px solid #333;"
            " border-radius: 4px; background: #1a1a14; color: #999; }"
            "QPushButton:hover { background: #1a1a1e; color: #ccccff; }"
        )
        self._gender_filter_btn_styles = {
            "all":    _gf_active_all,
            "male":   _gf_active_m,
            "female": _gf_active_f,
            "ditto":  _gf_active_d,
        }
        self._gender_filter_btn_normal = _gf_normal
        self._gender_filter_btns: dict[str, QPushButton] = {}

        for gf_key, gf_label in [
            ("all",    "⚥ All"),
            ("male",   "♂ Male"),
            ("female", "♀ Female"),
            ("ditto",  "🔀 Ditto"),
        ]:
            gb = QPushButton(gf_label)
            gb.setStyleSheet(_gf_active_all if gf_key == "all" else _gf_normal)
            gb.clicked.connect(lambda _=False, k=gf_key: self._set_gender_filter(k))
            self._gender_filter_btns[gf_key] = gb
            sgf_lay.addWidget(gb)

        sgf_lay.addStretch()
        sfb_root.addLayout(sgf_lay)

        # ── Row 3: sexuality filter ───────────────────────────────────
        ssf_lay = QHBoxLayout()
        ssf_lay.setContentsMargins(0, 0, 0, 0)
        ssf_lay.setSpacing(6)

        ssf_lbl = QLabel("Sexuality:")
        ssf_lbl.setStyleSheet("color: #888; font-size: 11px; background: transparent;")
        ssf_lay.addWidget(ssf_lbl)

        _sxf_active_all = (
            "QPushButton { font-size: 11px; padding: 2px 10px; border: 1px solid #e0c060;"
            " border-radius: 4px; background: #2a2510; color: #e0c060; font-weight: bold; }"
        )
        _sxf_active_gay = (
            "QPushButton { font-size: 11px; padding: 2px 10px; border: 1px solid #ff80ab;"
            " border-radius: 4px; background: #280018; color: #ff80ab; font-weight: bold; }"
        )
        _sxf_active_str = (
            "QPushButton { font-size: 11px; padding: 2px 10px; border: 1px solid #80d8ff;"
            " border-radius: 4px; background: #001828; color: #80d8ff; font-weight: bold; }"
        )
        _sxf_active_bi = (
            "QPushButton { font-size: 11px; padding: 2px 10px; border: 1px solid #ce93d8;"
            " border-radius: 4px; background: #1a0820; color: #ce93d8; font-weight: bold; }"
        )
        _sxf_normal = _gf_normal
        self._sexuality_filter_btn_styles = {
            "all":      _sxf_active_all,
            "gay":      _sxf_active_gay,
            "straight": _sxf_active_str,
            "bi":       _sxf_active_bi,
        }
        self._sexuality_filter_btn_normal = _sxf_normal
        self._sexuality_filter_btns: dict[str, QPushButton] = {}

        for sx_key, sx_label in [
            ("all",      "💕 All"),
            ("straight", "💙 Straight"),
            ("gay",      "🌈 Gay"),
            ("bi",       "💜 Bi"),
        ]:
            sb2 = QPushButton(sx_label)
            sb2.setStyleSheet(_sxf_active_all if sx_key == "all" else _sxf_normal)
            sb2.clicked.connect(lambda _=False, k=sx_key: self._set_sexuality_filter(k))
            self._sexuality_filter_btns[sx_key] = sb2
            ssf_lay.addWidget(sb2)

        ssf_lay.addStretch()
        sfb_root.addLayout(ssf_lay)

        self._sub_filter_bar.hide()

        # ── Advanced query builder bar (Newborns tab only) ────────────
        self._query_bar = _NewbornQueryBar(_get_query_presets_path())
        self._query_bar.changed.connect(self._rebuild_list)
        self._query_bar.hide()

        # ── Bank tag filter bar (hidden unless "bank" tab active) ────
        self._bank_tag_bar = QWidget()
        self._bank_tag_bar.setStyleSheet(
            "QWidget { background: #0e1a18; border-bottom: 1px solid #2a4030; }"
        )
        btb_lay = QHBoxLayout(self._bank_tag_bar)
        btb_lay.setContentsMargins(10, 4, 10, 4)
        btb_lay.setSpacing(6)
        btb_lbl = QLabel("Filter by tag:")
        btb_lbl.setStyleSheet("color: #60a070; font-size: 11px; background: transparent;")
        btb_lay.addWidget(btb_lbl)
        # The actual tag buttons are rebuilt dynamically via _rebuild_bank_tag_bar()
        self._bank_tag_btns_container = QWidget()
        self._bank_tag_btns_container.setStyleSheet("background: transparent;")
        self._bank_tag_btns_layout = QHBoxLayout(self._bank_tag_btns_container)
        self._bank_tag_btns_layout.setContentsMargins(0, 0, 0, 0)
        self._bank_tag_btns_layout.setSpacing(4)
        btb_lay.addWidget(self._bank_tag_btns_container, 1)
        self._bank_tag_bar.hide()
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

        self._detail = _CatDetail(ctrl=ctrl)
        self._detail.renamed.connect(self._on_cat_renamed)
        self._detail.banked.connect(self._on_cat_banked)
        self._detail.sent.connect(self._on_cat_sent)
        self._detail.moved.connect(self._on_cat_moved)
        self._detail.deleted.connect(self._on_cat_deleted)
        self._detail.disorder_removed.connect(self._on_cat_disorder_removed)
        self._detail.tagged.connect(self._on_cat_tagged)

        # ── Multi-select action bar (hidden until cats are selected) ─
        self._ms_bar = QWidget()
        self._ms_bar.setStyleSheet(
            "QWidget { background: #16162a; border-top: 1px solid #5555aa; }"
        )
        ms_lay = QHBoxLayout(self._ms_bar)
        ms_lay.setContentsMargins(8, 5, 8, 5)
        ms_lay.setSpacing(6)

        self._ms_count_lbl = QLabel("")
        self._ms_count_lbl.setStyleSheet(
            "color: #9999ff; font-size: 11px; font-weight: bold; background: transparent;"
        )
        ms_lay.addWidget(self._ms_count_lbl)
        ms_lay.addStretch()

        def _ms_btn(label, border, bg, fg):
            b = QPushButton(label)
            b.setStyleSheet(
                f"QPushButton {{ font-size: 11px; padding: 3px 10px; border: 1px solid {border};"
                f" border-radius: 4px; background: {bg}; color: {fg}; }}"
                f"QPushButton:hover {{ background: {bg}44; color: #fff; }}"
            )
            return b

        self._ms_bank_btn      = _ms_btn("🏦 Bank",       "#5555aa", "#1a1a3a", "#aaaaff")
        self._ms_unbank_btn    = _ms_btn("🏠 Unbank",     "#4caf50", "#1a2a1a", "#66cc66")
        self._ms_move_room_btn = _ms_btn("📍 Move Room",  "#3a8a3a", "#0e1a0e", "#88cc88")
        self._ms_gift_btn      = _ms_btn("🎁 Gift",       "#aa5555", "#2a1a1a", "#ff9999")
        self._ms_delete_btn    = _ms_btn("🗑 Delete",     "#992222", "#2a0a0a", "#cc4444")
        self._ms_tag_btn       = _ms_btn("🏷 Tag",        "#2a6040", "#0a1810", "#60b080")

        self._ms_bank_btn.clicked.connect(self._ms_do_bank)
        self._ms_unbank_btn.clicked.connect(self._ms_do_unbank)
        self._ms_move_room_btn.clicked.connect(self._ms_do_move_room)
        self._ms_gift_btn.clicked.connect(self._ms_do_send_gift)
        self._ms_delete_btn.clicked.connect(self._ms_do_delete)
        self._ms_tag_btn.clicked.connect(self._ms_do_tag)

        ms_lay.addWidget(self._ms_bank_btn)
        ms_lay.addWidget(self._ms_unbank_btn)
        ms_lay.addWidget(self._ms_move_room_btn)
        ms_lay.addWidget(self._ms_gift_btn)
        ms_lay.addWidget(self._ms_delete_btn)
        ms_lay.addWidget(self._ms_tag_btn)

        clear_ms_btn = QPushButton("✕")
        clear_ms_btn.setFixedSize(22, 22)
        clear_ms_btn.setToolTip("Clear selection")
        clear_ms_btn.setStyleSheet(
            "QPushButton { background: #333; border: 1px solid #666; border-radius: 4px;"
            " color: #aaa; font-size: 11px; padding: 0; }"
            "QPushButton:hover { background: #555; color: #fff; }"
        )
        clear_ms_btn.clicked.connect(self._clear_ms_selection)
        ms_lay.addWidget(clear_ms_btn)

        self._ms_bar.hide()

        left_frame = QWidget()
        lf_lay = QVBoxLayout(left_frame)
        lf_lay.setContentsMargins(0, 0, 0, 0)
        lf_lay.setSpacing(0)
        lf_lay.addWidget(list_scroll, 1)
        lf_lay.addWidget(self._ms_bar)

        splitter.addWidget(left_frame)
        splitter.addWidget(self._detail)
        splitter.setSizes([320, 730])
        splitter.setHandleWidth(4)

        root_lay = QVBoxLayout(self)
        root_lay.setContentsMargins(0, 0, 0, 0)
        root_lay.setSpacing(0)
        root_lay.addWidget(filter_bar)
        root_lay.addWidget(self._sub_filter_bar)
        root_lay.addWidget(self._query_bar)
        root_lay.addWidget(self._bank_tag_bar)
        root_lay.addWidget(splitter, 1)

        self._rebuild_list()

    # ── Filter ───────────────────────────────────────────────────────

    def _set_filter(self, key: str):
        self._filter = key
        _newborn_active = (
            "QPushButton { font-size: 12px; padding: 3px 12px; border: 1px solid #e0c060;"
            " border-radius: 4px; background: #2a2510; color: #e0c060; font-weight: bold; }"
        )
        _newborn_normal = (
            "QPushButton { font-size: 12px; padding: 3px 12px; border: 1px solid #444;"
            " border-radius: 4px; background: #1e1e1e; color: #aaa; }"
            "QPushButton:hover { background: #282820; color: #e0c060; }"
        )
        for k, btn in self._filter_btns.items():
            if k == "newborns":
                btn.setStyleSheet(_newborn_active if k == key else _newborn_normal)
            else:
                btn.setStyleSheet(
                    self._filter_btn_active_style if k == key
                    else self._filter_btn_normal_style
                )
        # Show/hide sub-filter bar
        if key == "newborns":
            self._sub_filter_bar.show()
            self._query_bar.show()
            self._bank_tag_bar.hide()
            self._refresh_kill_counter()
        elif key == "bank":
            self._sub_filter_bar.hide()
            self._query_bar.hide()
            self._bank_tag_bar.show()
            self._rebuild_bank_tag_bar()
        else:
            self._sub_filter_bar.hide()
            self._query_bar.hide()
            self._bank_tag_bar.hide()
            # Reset all sub-filters so they're clean next time
            self._sub_filter       = "all"
            self._gender_filter    = "all"
            self._sexuality_filter = "all"
            for k, btn in self._sub_filter_btns.items():
                btn.setStyleSheet(
                    self._sub_filter_btn_active_style if k == "all"
                    else self._sub_filter_btn_normal_style
                )
            for k, btn in self._gender_filter_btns.items():
                btn.setStyleSheet(
                    self._gender_filter_btn_styles["all"] if k == "all"
                    else self._gender_filter_btn_normal
                )
            for k, btn in self._sexuality_filter_btns.items():
                btn.setStyleSheet(
                    self._sexuality_filter_btn_styles["all"] if k == "all"
                    else self._sexuality_filter_btn_normal
                )
        self._clear_ms_selection()
        self._rebuild_list()

    def _set_sub_filter(self, key: str):
        self._sub_filter = key
        for k, btn in self._sub_filter_btns.items():
            btn.setStyleSheet(
                self._sub_filter_btn_active_style if k == key
                else self._sub_filter_btn_normal_style
            )
        self._rebuild_list()

    def _set_gender_filter(self, key: str):
        self._gender_filter = key
        for k, btn in self._gender_filter_btns.items():
            btn.setStyleSheet(
                self._gender_filter_btn_styles.get(k, self._gender_filter_btn_normal)
                if k == key else self._gender_filter_btn_normal
            )
        self._rebuild_list()

    def _set_sexuality_filter(self, key: str):
        self._sexuality_filter = key
        for k, btn in self._sexuality_filter_btns.items():
            btn.setStyleSheet(
                self._sexuality_filter_btn_styles.get(k, self._sexuality_filter_btn_normal)
                if k == key else self._sexuality_filter_btn_normal
            )
        self._rebuild_list()

    def _rebuild_bank_tag_bar(self):
        """Rebuild the tag buttons in the bank tag filter bar from current cat tags."""
        # Clear old buttons
        while self._bank_tag_btns_layout.count():
            item = self._bank_tag_btns_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        # Collect all tags from banked cats
        all_tags: list[str] = []
        seen: set[str] = set()
        for cat in self._cats:
            if cat.status == "In Bank":
                for t in getattr(cat, "tags", []):
                    if t not in seen:
                        all_tags.append(t)
                        seen.add(t)
        all_tags.sort()

        _tag_active = (
            "QPushButton { font-size: 11px; padding: 2px 10px; border: 1px solid #4caf80;"
            " border-radius: 4px; background: #0e2a18; color: #4cef90; font-weight: bold; }"
        )
        _tag_normal = (
            "QPushButton { font-size: 11px; padding: 2px 10px; border: 1px solid #2a4030;"
            " border-radius: 4px; background: #0a1810; color: #60a070; }"
            "QPushButton:hover { background: #102018; color: #80e0a0; }"
        )

        # "All" button
        all_btn = QPushButton("🐱 All")
        all_btn.setStyleSheet(_tag_active if self._tag_filter == "all" else _tag_normal)
        all_btn.clicked.connect(lambda: self._set_tag_filter("all"))
        self._bank_tag_btns_layout.addWidget(all_btn)

        # "No Tags" button — fixed special value, always shown
        _notag_active = (
            "QPushButton { font-size: 11px; padding: 2px 10px; border: 1px solid #886644;"
            " border-radius: 4px; background: #221808; color: #ccaa66; font-weight: bold; }"
        )
        _notag_normal = (
            "QPushButton { font-size: 11px; padding: 2px 10px; border: 1px solid #443322;"
            " border-radius: 4px; background: #141008; color: #886644; }"
            "QPushButton:hover { background: #1e1610; color: #ccaa66; }"
        )
        notag_btn = QPushButton("🚫 No Tags")
        notag_btn.setStyleSheet(_notag_active if self._tag_filter == "__no_tags__" else _notag_normal)
        notag_btn.clicked.connect(lambda: self._set_tag_filter("__no_tags__"))
        self._bank_tag_btns_layout.addWidget(notag_btn)

        for tag in all_tags:
            btn = QPushButton(f"🏷 {tag}")
            btn.setStyleSheet(_tag_active if self._tag_filter == tag else _tag_normal)
            btn.clicked.connect(lambda _=False, t=tag: self._set_tag_filter(t))
            self._bank_tag_btns_layout.addWidget(btn)

        self._bank_tag_btns_layout.addStretch()

    def _set_tag_filter(self, tag: str):
        """Set the active tag filter for the bank view and rebuild the list."""
        self._tag_filter = tag
        self._rebuild_bank_tag_bar()
        self._rebuild_list()

    def _filtered_cats(self) -> list:
        from utils.cat_filters import filter_cats
        cats = filter_cats(
            self._cats,
            self._filter,
            sub_filter=self._sub_filter,
            gender_filter=self._gender_filter,
            sexuality_filter=self._sexuality_filter,
            tag_filter=self._tag_filter,
        )
        # Apply advanced query builder filter (Newborns tab only)
        if self._filter == "newborns":
            from utils.cat_query_filters import filter_cats_query
            query_group = self._query_bar.get_filter_group()
            if query_group is not None:
                cats = filter_cats_query(cats, query_group)
        return cats

    # ── List ─────────────────────────────────────────────────────────

    def _rebuild_list(self):
        while self._list_layout.count():
            item = self._list_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        self._active_card = None
        # Keep ms_selected set intact across rebuilds — only clear it explicitly

        cats = self._filtered_cats()
        self._count_lbl.setText(f"{len(cats)} cat(s)")

        if not cats:
            empty = QLabel("No cats found.")
            empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
            empty.setStyleSheet("color: #555; font-size: 13px; padding: 30px;")
            self._list_layout.addWidget(empty)
            self._refresh_ms_bar()
            return

        def _add_card(cat):
            card = _CatCard(cat)
            card.selected.connect(self._on_cat_selected)
            card.ms_toggled.connect(self._on_card_ms_toggled)
            if cat in self._ms_selected:
                card.set_ms_selected(True)
            self._list_layout.addWidget(card)

        if self._filter in ("house", "bank"):
            # Group by room, rooms sorted alphabetically; cats within each room also sorted
            rooms: dict[str, list] = {}
            for cat in sorted(cats, key=lambda c: ((c.room or "").lower(), (c.name or "").lower())):
                key = cat.room or "(No room)"
                rooms.setdefault(key, []).append(cat)

            for room_name, room_cats in rooms.items():
                all_sel = all(c in self._ms_selected for c in room_cats)
                header = _RoomHeader(room_name, len(room_cats), all_selected=all_sel)
                header.select_all_clicked.connect(self._on_select_room)
                self._list_layout.addWidget(header)
                for cat in room_cats:
                    _add_card(cat)
        elif self._filter == "newborns":
            # Sort by mutation count descending, then name
            for cat in sorted(
                cats,
                key=lambda c: (-len(getattr(c, "mutation_chip_items", [])), (c.name or "").lower())
            ):
                _add_card(cat)
        else:
            for cat in sorted(cats, key=lambda c: (c.name or "").lower()):
                _add_card(cat)

        self._list_layout.addStretch()
        self._refresh_ms_bar()

    def _on_cat_selected(self, cat):
        # Clear ms selection on a normal (non-Ctrl) click
        self._clear_ms_selection()

        if self._active_card is not None:
            self._active_card.set_active(False)

        for i in range(self._list_layout.count()):
            item = self._list_layout.itemAt(i)
            if item and item.widget() and isinstance(item.widget(), _CatCard):
                card = item.widget()
                if card._cat is cat:
                    card.set_active(True)
                    self._active_card = card
                    break

        self._detail.show_cat(cat)

    # ── Multi-select ─────────────────────────────────────────────────

    def _on_card_ms_toggled(self, cat, is_selected: bool):
        """Called when a card is Ctrl+clicked."""
        if is_selected:
            self._ms_selected.add(cat)
        else:
            self._ms_selected.discard(cat)

        # Update the card visual
        for i in range(self._list_layout.count()):
            item = self._list_layout.itemAt(i)
            if item and item.widget() and isinstance(item.widget(), _CatCard):
                card = item.widget()
                if card._cat is cat:
                    card.set_ms_selected(is_selected)
                    break

        # Refresh action bar + room header states
        self._refresh_ms_bar()

    def _clear_ms_selection(self):
        """Deselect all multi-selected cats and hide the action bar."""
        self._ms_selected.clear()
        for i in range(self._list_layout.count()):
            item = self._list_layout.itemAt(i)
            if item and item.widget() and isinstance(item.widget(), _CatCard):
                item.widget().set_ms_selected(False)
        self._ms_bar.hide()

    def _refresh_ms_bar(self):
        """Show / hide the action bar and update button visibility based on current filter."""
        n = len(self._ms_selected)
        if n == 0:
            self._ms_bar.hide()
            return

        self._ms_count_lbl.setText(
            f"{n} cat{'s' if n > 1 else ''} selected  —  Ctrl+click to add/remove"
        )
        is_house    = self._filter == "house"
        is_bank     = self._filter == "bank"
        is_newborns = self._filter == "newborns"

        has_house = any(c.status == "In House" for c in self._ms_selected)
        has_bank  = any(c.status == "In Bank"  for c in self._ms_selected)

        if is_newborns:
            self._ms_bank_btn.setVisible(has_house)
            self._ms_unbank_btn.setVisible(has_bank)
            self._ms_move_room_btn.setVisible(has_house)
            self._ms_gift_btn.setVisible(has_house or has_bank)
            self._ms_delete_btn.setVisible(True)
            self._ms_tag_btn.setVisible(False)
        else:
            self._ms_bank_btn.setVisible(is_house)
            self._ms_unbank_btn.setVisible(is_bank)
            self._ms_move_room_btn.setVisible(is_house)
            self._ms_gift_btn.setVisible(is_house or is_bank)
            self._ms_delete_btn.setVisible(False)
            self._ms_tag_btn.setVisible(is_bank)

        self._ms_bar.show()

        # Refresh "Select all / Deselect all" label on room headers
        self._refresh_room_header_states()

    def _refresh_room_header_states(self):
        """Update each room header's button label to reflect current ms-selection state."""
        # Collect cats per room from current layout (already computed during _rebuild_list)
        room_cats: dict[str, list] = {}
        current_room: str | None = None
        for i in range(self._list_layout.count()):
            widget = self._list_layout.itemAt(i).widget()
            if isinstance(widget, _RoomHeader):
                current_room = widget._room_name
                room_cats[current_room] = []
            elif isinstance(widget, _CatCard) and current_room is not None:
                room_cats[current_room].append(widget._cat)

        for i in range(self._list_layout.count()):
            widget = self._list_layout.itemAt(i).widget()
            if isinstance(widget, _RoomHeader):
                rname = widget._room_name
                cats_in_room = room_cats.get(rname, [])
                all_sel = bool(cats_in_room) and all(c in self._ms_selected for c in cats_in_room)
                widget.set_all_selected(all_sel)

    def _on_select_room(self, room_name: str):
        """Toggle selection for all cats in *room_name* (select all / deselect all)."""
        cats_in_room = [
            c for c in self._filtered_cats()
            if (c.room or "(No room)") == room_name
        ]
        if not cats_in_room:
            return

        all_already_selected = all(c in self._ms_selected for c in cats_in_room)

        if all_already_selected:
            # Deselect all in this room
            for cat in cats_in_room:
                self._ms_selected.discard(cat)
        else:
            # Select all in this room
            for cat in cats_in_room:
                self._ms_selected.add(cat)

        # Update card visuals
        for i in range(self._list_layout.count()):
            item = self._list_layout.itemAt(i)
            if item and item.widget() and isinstance(item.widget(), _CatCard):
                card = item.widget()
                if (card._cat.room or "(No room)") == room_name:
                    card.set_ms_selected(card._cat in self._ms_selected)

        self._refresh_ms_bar()

    def _ms_do_bank(self):
        """Bank all currently ms-selected In-House cats."""
        cats = list(self._ms_selected)
        if not cats:
            return
        names = ", ".join(c.name for c in cats)
        reply = QMessageBox.question(
            self, "Bank Selected Cats",
            f"Send <b>{len(cats)}</b> cat(s) to the cat bank?<br><br>{names}",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        try:
            count = self._ctrl.apply_bank_cats_multiple(cats)
        except Exception as exc:
            QMessageBox.critical(self, "Error", str(exc))
            return
        self._ms_selected.clear()
        self._rebuild_list()
        self._detail.clear()
        QMessageBox.information(self, "Done", f"{count} cat(s) sent to the cat bank.")

    def _ms_do_unbank(self):
        """Unbank all currently ms-selected In-Bank cats."""
        cats = list(self._ms_selected)
        if not cats:
            return
        names = ", ".join(c.name for c in cats)
        reply = QMessageBox.question(
            self, "Move to House",
            f"Move <b>{len(cats)}</b> cat(s) back to the house?<br><br>{names}",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        try:
            count = self._ctrl.apply_unbank_cats_multiple(cats)
        except Exception as exc:
            QMessageBox.critical(self, "Error", str(exc))
            return
        self._ms_selected.clear()
        self._rebuild_list()
        self._detail.clear()
        QMessageBox.information(self, "Done", f"{count} cat(s) moved back to the house.")

    def _ms_do_send_gift(self):
        """Send all ms-selected cats as gifts to the partner."""
        cats = list(self._ms_selected)
        if not cats:
            return
        if self._ctrl is None:
            return
        try:
            ctx = self._ctrl.get_gift_context()
        except Exception as exc:
            QMessageBox.critical(self, "Error", str(exc))
            return
        if not ctx.get("is_known_user"):
            QMessageBox.warning(
                self, "Cannot Send Gift",
                "Your save file's Steam ID was not recognised.\n"
                "Gift features require a known user pair configured in version.py."
            )
            return
        names = ", ".join(c.name for c in cats)
        reply = QMessageBox.question(
            self, "🎁 Send Cats",
            f"Send <b>{len(cats)}</b> cat(s) to <b>{ctx['recipient_name']}</b>?<br><br>"
            f"{names}<br><br>The cats will be removed from your save.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        try:
            count = self._ctrl.apply_send_cats_multiple(cats)
        except Exception as exc:
            QMessageBox.critical(self, "Send Failed", str(exc))
            return
        self._ms_selected.clear()
        self._rebuild_list()
        self._detail.clear()
        QMessageBox.information(
            self, "Cats Sent",
            f"<b>{count}</b> cat(s) sent to {ctx['recipient_name']}!"
        )

    def _on_cat_renamed(self, cat):
        """Called after a successful rename: update the card label in-place."""
        for i in range(self._list_layout.count()):
            item = self._list_layout.itemAt(i)
            if item and item.widget() and isinstance(item.widget(), _CatCard):
                card = item.widget()
                if card._cat is cat:
                    card.update_name()
                    break
        # Re-sort the list now that the name changed
        self._rebuild_list()
        # Re-select the cat in the new sorted order
        self._reselect_cat(cat)

    def _on_cat_banked(self, cat):
        """Called after a bank / unbank action: rebuild the list and reselect the cat."""
        self._ms_selected.discard(cat)
        self._rebuild_list()
        self._reselect_cat(cat)

    def _on_cat_sent(self, cat):
        """Called after a cat gift is sent: rebuild the list (cat is now Gone)."""
        self._ms_selected.discard(cat)
        self._rebuild_list()
        self._detail.clear()

    def _on_cat_moved(self, cat):
        """Called after a room move: rebuild the list and reselect the cat."""
        self._rebuild_list()
        self._reselect_cat(cat)

    def _on_cat_disorder_removed(self, cat):
        """Called after a disorder is removed from a cat: rebuild list and refresh detail."""
        self._rebuild_list()
        self._reselect_cat(cat)

    def _on_cat_deleted(self, cat, kill_count: int, gold_awarded: int):
        """Called after a newborn is trashed (marked Gone, row kept in DB)."""
        self._ms_selected.discard(cat)
        self._rebuild_list()   # cat is now Gone — excluded from newborns filter
        self._detail.clear()
        self._refresh_kill_counter()
        if gold_awarded:
            QMessageBox.information(
                self, "🪙 Reward!",
                f"10 newborns trashed!<br><b>+{gold_awarded} gold</b> added to your save.",
            )

    def _ms_do_move_room(self):
        """Move all ms-selected In-House cats to a chosen room."""
        house_cats = [c for c in self._ms_selected if c.status == "In House"]
        if not house_cats or self._ctrl is None:
            return
        rooms = self._ctrl.get_available_rooms()
        if not rooms:
            QMessageBox.information(self, "No Rooms", "No rooms found in the current house state.")
            return
        from PySide6.QtWidgets import QInputDialog
        display_names = [_room_display(r) for r in rooms]
        dlg = QInputDialog(self)
        dlg.setWindowTitle("Move to Room")
        dlg.setLabelText(f"Choose destination room for {len(house_cats)} cat(s):")
        dlg.setComboBoxItems(display_names)
        dlg.setComboBoxEditable(False)
        dlg.setMinimumWidth(360)
        ok = dlg.exec()
        display = dlg.textValue()
        if not ok or not display:
            return
        # Map display name back to internal room key
        room = rooms[display_names.index(display)] if display in display_names else display
        try:
            moved = self._ctrl.apply_move_cats_room_multiple(house_cats, room)
        except Exception as exc:
            QMessageBox.critical(self, "Move Failed", str(exc))
            return
        self._rebuild_list()
        QMessageBox.information(self, "Done", f"{moved} cat(s) moved to <b>{_room_display(room)}</b>.")

    def _ms_do_delete(self):
        """Delete all ms-selected newborns."""
        cats = list(self._ms_selected)
        if not cats or self._ctrl is None:
            return
        kills_now   = getattr(self._ctrl, "newborn_kill_count", 0)
        next_reward = 10 - (kills_now % 10)
        reply = QMessageBox.question(
            self, "🗑 Delete Newborns",
            f"<b>Permanently delete {len(cats)} newborn(s)?</b><br><br>"
            f"This cannot be undone.<br>"
            f"Kill counter: <b>{kills_now}</b> — "
            f"next 🪙 25 gold in <b>{next_reward}</b> more kill(s).",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        try:
            n_deleted, total_gold = self._ctrl.apply_delete_cats_multiple(cats)
        except Exception as exc:
            QMessageBox.critical(self, "Delete Failed", str(exc))
            return
        self._ms_selected.clear()
        self._rebuild_list()
        self._detail.clear()
        self._refresh_kill_counter()
        msg = f"<b>{n_deleted}</b> newborn(s) deleted."
        if total_gold:
            msg += f"<br>🪙 <b>+{total_gold} gold</b> rewarded!"
        QMessageBox.information(self, "Done", msg)

    def _ms_do_tag(self):
        """Open a bulk tag dialog for all currently ms-selected cats."""
        cats = list(self._ms_selected)
        if not cats or self._ctrl is None:
            return

        from PySide6.QtWidgets import (
            QDialog, QVBoxLayout, QLabel, QLineEdit,
            QDialogButtonBox, QCheckBox
        )

        # Collect current tags across selected cats
        all_tags_in_use: list[str] = self._ctrl.get_all_cat_tags()
        # Per-cat tags: tags that ALL selected cats have vs. tags that SOME have
        all_sets = [set(getattr(c, "tags", [])) for c in cats]
        common_tags = set.intersection(*all_sets) if all_sets else set()

        dlg = QDialog(self)
        dlg.setWindowTitle(f"🏷 Tag {len(cats)} cat(s)")
        dlg.setMinimumWidth(320)
        dlg.setStyleSheet("QDialog { background: #1a1a1a; color: #ddd; }")
        dlg_lay = QVBoxLayout(dlg)
        dlg_lay.setSpacing(10)

        info_lbl = QLabel(
            f"Manage tags for <b>{len(cats)}</b> cat(s).<br>"
            "Checked tags will be <b>added</b> to all; unchecked will be <b>removed</b>."
        )
        info_lbl.setWordWrap(True)
        info_lbl.setStyleSheet("color: #aaa; font-size: 11px; background: transparent;")
        dlg_lay.addWidget(info_lbl)

        # Checkboxes for existing tags
        checkboxes: list[QCheckBox] = []
        if all_tags_in_use:
            tags_lbl = QLabel("Existing tags:")
            tags_lbl.setStyleSheet("color: #80e0a0; font-size: 11px; background: transparent;")
            dlg_lay.addWidget(tags_lbl)
            for tag in all_tags_in_use:
                cb = QCheckBox(tag)
                cb.setStyleSheet("color: #ddd; font-size: 11px;")
                cb.setChecked(tag in common_tags)
                cb.setProperty("tag_name", tag)
                dlg_lay.addWidget(cb)
                checkboxes.append(cb)

        # New tag input
        new_lbl = QLabel("New tag (optional):")
        new_lbl.setStyleSheet("color: #80e0a0; font-size: 11px; background: transparent;")
        dlg_lay.addWidget(new_lbl)
        new_edit = QLineEdit()
        new_edit.setStyleSheet(
            "QLineEdit { background: #111; border: 1px solid #2a6040; border-radius: 4px;"
            " color: #ccc; padding: 3px 6px; }"
        )
        new_edit.setPlaceholderText("Type a new tag name…")
        dlg_lay.addWidget(new_edit)

        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        btns.setStyleSheet("color: #ccc;")
        btns.accepted.connect(dlg.accept)
        btns.rejected.connect(dlg.reject)
        dlg_lay.addWidget(btns)

        if dlg.exec() != QDialog.DialogCode.Accepted:
            return

        add_tags: list[str]    = []
        remove_tags: list[str] = []
        for cb in checkboxes:
            tag = cb.property("tag_name")
            if cb.isChecked():
                add_tags.append(tag)
            else:
                remove_tags.append(tag)

        new_tag = new_edit.text().strip()
        if new_tag:
            add_tags.append(new_tag)

        if not add_tags and not remove_tags:
            return

        try:
            modified = self._ctrl.apply_set_cats_tags_bulk(cats, add_tags, remove_tags)
        except Exception as exc:
            QMessageBox.critical(self, "Tag Error", str(exc))
            return

        self._rebuild_list()
        self._rebuild_bank_tag_bar()
        if self._active_card is not None:
            self._detail.show_cat(self._active_card._cat)
        QMessageBox.information(self, "Tags Updated", f"Tags updated for <b>{modified}</b> cat(s).")

    def _on_cat_tagged(self, cat):
        """Called after a tag is added/removed from the detail panel."""
        self._rebuild_list()
        self._rebuild_bank_tag_bar()
        self._reselect_cat(cat)

    def _refresh_kill_counter(self):
        """Update the kill counter label in the sub-filter bar."""
        if self._ctrl is None:
            self._kill_count_lbl.setText("")
            return
        kills = getattr(self._ctrl, "newborn_kill_count", 0)
        remaining = 10 - (kills % 10)
        if kills == 0:
            self._kill_count_lbl.setText("")
        elif remaining == 10:
            self._kill_count_lbl.setText(f"💀 {kills} killed  🪙 +25 gold just awarded!")
        else:
            self._kill_count_lbl.setText(f"💀 {kills} killed  ({remaining} until 🪙 +25g)")

    def _on_remove_blood_frenzy(self):
        """Remove the BloodFrenzy disorder from cats in the currently active filter tab."""
        if self._ctrl is None:
            return
        current_cats = self._filtered_cats()
        affected = [
            c for c in current_cats
            if "BloodFrenzy" in getattr(c, "disorders", [])
        ]
        if not affected:
            QMessageBox.information(
                self, "Remove BloodFrenzy",
                "No cats in the current tab have BloodFrenzy.",
            )
            return
        tab_label = {
            "house":     "🏠 In House",
            "adventure": "⚔️ Adventure",
            "bank":      "🏦 In Bank",
            "newborns":  "🍼 Newborns",
        }.get(self._filter, self._filter)
        names_html = "<br>".join(f"• {c.name}" for c in affected)
        reply = QMessageBox.question(
            self, "Remove BloodFrenzy",
            f"<b>Remove BloodFrenzy from {len(affected)} cat(s) in [{tab_label}]?</b>"
            f"<br><br>{names_html}<br><br>"
            f"This will permanently modify their save data.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        try:
            n_modified, n_targeted = self._ctrl.apply_remove_disorder_bulk(
                "BloodFrenzy", cats=current_cats
            )
        except Exception as exc:
            QMessageBox.critical(self, "Error", f"Could not remove BloodFrenzy:\n{exc}")
            return
        QMessageBox.information(
            self, "Done",
            f"BloodFrenzy removed from <b>{n_modified}</b> cat(s) "
            f"(checked {n_targeted} cats in [{tab_label}]).",
        )
        self._rebuild_list()
        if self._active_card is not None:
            self._detail.show_cat(self._active_card._cat)

    def _on_receive_cats(self):
        """Receive pending cat gifts from the partner and add them to the cat bank."""
        if self._ctrl is None:
            return
        try:
            received = self._ctrl.apply_receive_cats()
        except Exception as exc:
            QMessageBox.critical(self, "Receive Failed", f"Could not receive cats:\n{exc}")
            return

        if not received:
            QMessageBox.information(self, "Receive Cats", "No pending cat gifts.")
            return

        # Rebuild list so received cats appear in the Bank filter
        self._rebuild_list()

        names_html = "<br>".join(f"• {c.name}" for c in received)
        QMessageBox.information(
            self,
            "Cats Received!",
            f"<b>{len(received)}</b> cat(s) added to the Cat Bank:<br><br>{names_html}",
        )

        # Switch to the Bank filter so the user sees the new cats immediately
        self._set_filter("bank")

    def _reselect_cat(self, cat):
        """Find the card for *cat* in the (possibly re-sorted) list and activate it."""
        for i in range(self._list_layout.count()):
            item = self._list_layout.itemAt(i)
            if item and item.widget() and isinstance(item.widget(), _CatCard):
                card = item.widget()
                if card._cat is cat:
                    card.set_active(True)
                    self._active_card = card
                    self._detail.show_cat(cat)
                    break

    # ── Public refresh ────────────────────────────────────────────────

    def refresh(self, cats: list):
        """Update the cat list (called when the main window reloads)."""
        self._cats = cats
        self._ms_selected.clear()
        self._rebuild_list()
