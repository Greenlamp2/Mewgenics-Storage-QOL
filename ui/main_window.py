import os

from PySide6.QtCore import Qt, QSize, QTimer, QPoint
from PySide6.QtGui import QPixmap, QPainter, QIcon
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QHBoxLayout, QVBoxLayout,
    QLabel, QFrame, QSplitter,
    QScrollArea, QGridLayout, QToolButton, QTabBar, QPushButton, QMessageBox,
    QApplication,
)

from parse.item import Item, GhostItem
from catalogs.itemcatalog import item_catalog
from utils.loaders import RARITIES
from app_controller import AppController, EXCLUDED_RARITIES
from version import APP_VERSION

# mapping tab label → save_inventories key
TAB_TO_INV_KEY = {"Storage": "storage", "Trash": "trash"}

DEBUG_MODE = False   # passer à True pour activer les actions de debug (ex: Clone to Storage depuis Pool)

ICON_DIR    = os.path.join(os.path.dirname(os.path.dirname(__file__)), "assets", "img")
MONEY_ICON  = os.path.join(os.path.dirname(os.path.dirname(__file__)), "assets", "icons", "money.png")
TOKENS_DIR  = os.path.join(os.path.dirname(os.path.dirname(__file__)), "assets", "icons", "tokens")
GRID_COLS = 7
ICON_SIZE = 56

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
    "common":               "rgba(208, 208, 208, 0.18)",
    "uncommon":             "rgba(136, 136, 136, 0.25)",
    "rare":                 "rgba(200, 168, 48,  0.25)",
    "very_rare":            "rgba(192,  64, 64,  0.28)",
    "consumable_common":    "rgba(208, 208, 208, 0.18)",
    "consumable_uncommon":  "rgba(136, 136, 136, 0.25)",
    "consumable_rare":      "rgba(200, 168, 48,  0.25)",
    "consumable_very_rare": "rgba(192,  64, 64,  0.28)",
}

RARITY_ORDER = {
    "common": 0, "consumable_common": 0,
    "uncommon": 1, "consumable_uncommon": 1,
    "rare": 2, "consumable_rare": 2,
    "very_rare": 3, "consumable_very_rare": 3,
}
SORT_KEYS    = ("default", "name", "rarity", "category")

# Cell size used both by QGridLayout items and VirtualItemGrid
CELL_SIZE = ICON_SIZE + 8 + 4   # button (ICON_SIZE+8) + grid spacing (4)


# ──────────────────────────────────────────────────────────────────────────────
# Virtual scroll grid — renders only visible rows
# ──────────────────────────────────────────────────────────────────────────────

class VirtualItemGrid(QWidget):
    """Fixed-height widget that creates/hides item buttons on demand as the user scrolls."""

    BUFFER_ROWS = 2   # extra rows to keep alive above and below the viewport

    def __init__(self, indexed: list, items_list, make_btn_cb):
        """
        indexed   : list of (orig_idx, item) pairs in display order
        items_list: the original items list (passed through to on_select callback)
        make_btn_cb: callable(orig_idx, item, items_list) → QToolButton (without parent)
        """
        super().__init__()
        self._indexed     = indexed
        self._items_list  = items_list
        self._make_btn    = make_btn_cb
        self._btns: dict[int, QToolButton] = {}
        self._scroll_area = None

        n          = len(indexed)
        self._rows = max(1, (n + GRID_COLS - 1) // GRID_COLS)
        self.setFixedHeight(self._rows * CELL_SIZE + 8)

    def attach(self, scroll_area: QScrollArea):
        self._scroll_area = scroll_area
        scroll_area.verticalScrollBar().valueChanged.connect(self._refresh)
        QTimer.singleShot(0, self._refresh)   # first paint after layout settles

    def _visible_idx_set(self) -> set:
        sa = self._scroll_area
        if sa is None:
            return set(range(len(self._indexed)))

        content = sa.widget()
        if content is None:
            return set()

        widget_top = self.mapTo(content, QPoint(0, 0)).y()
        scroll_y   = sa.verticalScrollBar().value()
        view_h     = sa.viewport().height()

        local_top    = scroll_y - widget_top
        local_bottom = local_top + view_h

        first_row = max(0,              int(local_top    / CELL_SIZE) - self.BUFFER_ROWS)
        last_row  = min(self._rows - 1, int(local_bottom / CELL_SIZE) + self.BUFFER_ROWS)

        visible: set[int] = set()
        for row in range(first_row, last_row + 1):
            for col in range(GRID_COLS):
                idx = row * GRID_COLS + col
                if idx < len(self._indexed):
                    visible.add(idx)
        return visible

    def _refresh(self):
        visible = self._visible_idx_set()

        # Show / create visible buttons
        for idx in visible:
            if idx not in self._btns:
                self._spawn(idx)
            else:
                self._btns[idx].show()

        # Hide out-of-view buttons (keep alive to avoid re-rendering SVGs)
        for idx, btn in self._btns.items():
            if idx not in visible:
                btn.hide()

    def _spawn(self, idx: int):
        orig_idx, item = self._indexed[idx]
        btn = self._make_btn(orig_idx, item, self._items_list)
        btn.setParent(self)
        row = idx // GRID_COLS
        col = idx % GRID_COLS
        btn.move(col * CELL_SIZE + 4, row * CELL_SIZE + 4)
        btn.show()
        self._btns[idx] = btn

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._refresh()


def broken_overlay_pixmap(pixmap: QPixmap) -> QPixmap:
    """Return a copy of *pixmap* with a broken overlay (semi-transparent dark tint + red X)."""
    from PySide6.QtGui import QPen, QColor
    result = QPixmap(pixmap.size())
    result.fill(Qt.GlobalColor.transparent)
    painter = QPainter(result)
    painter.drawPixmap(0, 0, pixmap)
    # Semi-transparent dark tint (icon still visible underneath)
    painter.fillRect(result.rect(), QColor(0, 0, 0, 140))
    # Red X lines
    pen = QPen(QColor(220, 40, 40), max(2, pixmap.width() // 14))
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    painter.setPen(pen)
    m = pixmap.width() // 5
    painter.drawLine(m, m, pixmap.width() - m, pixmap.height() - m)
    painter.drawLine(pixmap.width() - m, m, m, pixmap.height() - m)
    painter.end()
    return result


def locked_overlay_pixmap(pixmap: QPixmap) -> QPixmap:
    """Return a desaturated, darkened copy of *pixmap* for undiscovered items."""
    from PySide6.QtGui import QColor
    result = QPixmap(pixmap.size())
    result.fill(Qt.GlobalColor.transparent)
    painter = QPainter(result)
    painter.setOpacity(0.30)
    painter.drawPixmap(0, 0, pixmap)
    painter.setOpacity(1.0)
    painter.fillRect(result.rect(), QColor(15, 15, 25, 140))
    painter.end()
    return result


def svg_to_pixmap(svg_path: str, size: int) -> QPixmap:
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    if os.path.exists(svg_path):
        renderer = QSvgRenderer(svg_path)
        painter = QPainter(pixmap)
        renderer.render(painter)
        painter.end()
    return pixmap


class MainWindow(QMainWindow):
    def __init__(self, sav_path: str):
        super().__init__()
        self.setWindowTitle(f"Mewgenics Storage QOL  {APP_VERSION}")
        self.resize(960, 640)

        self.sav_path = sav_path
        self.ctrl = AppController(sav_path)

        self._selected_item_idx: int | None = None
        self._selected_inv_key: str | None = None
        self._selected_btn: QToolButton | None = None
        self._sort_key: str = "default"
        self._multi_selection: dict[int, QToolButton] = {}

        self.ctrl.load_data()
        self._build_ui()
        self._build_gold_bar()
        self._build_overlay()
        self._refresh_pool_tab_title()
        self._populate(self.ctrl.inv_items["Storage"])
        QTimer.singleShot(0, self._show_overlay)

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self):
        splitter = QSplitter(Qt.Orientation.Horizontal)

        # ── Left: tab bar + icon grid ─────────────────────────────────
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(0)

        self.tab_bar = QTabBar()
        for label in self.ctrl.inv_items:
            self.tab_bar.addTab(label)
        self.tab_bar.currentChanged.connect(self._on_tab_changed)

        # ── Sort toolbar ──────────────────────────────────────────────
        sort_bar = QWidget()
        sort_layout = QHBoxLayout(sort_bar)
        sort_layout.setContentsMargins(6, 3, 6, 3)
        sort_layout.setSpacing(4)
        sort_layout.addWidget(QLabel("Sort:"))

        _btn_base = (
            "QPushButton { font-size: 11px; padding: 2px 8px;"
            " border: 1px solid #555; border-radius: 3px; background: #2d2d2d; color: #ccc; }"
            "QPushButton:hover { background: #3a3a3a; }"
        )
        _btn_active = (
            "QPushButton { font-size: 11px; font-weight: bold; padding: 2px 8px;"
            " border: 1px solid #4a9eff; border-radius: 3px; background: #1a3a5c; color: #4a9eff; }"
        )
        self._sort_btns: dict[str, QPushButton] = {}
        self._sort_btn_styles = (_btn_base, _btn_active)
        for key in SORT_KEYS:
            btn = QPushButton(key.capitalize())
            btn.setStyleSheet(_btn_active if key == self._sort_key else _btn_base)
            btn.clicked.connect(lambda _=False, k=key: self._set_sort(k))
            self._sort_btns[key] = btn
            sort_layout.addWidget(btn)
        sort_layout.addStretch()

        self.sacrifice_all_btn = QPushButton("✦ Sacrifice All → Tokens")
        self.sacrifice_all_btn.setVisible(False)
        self.sacrifice_all_btn.setStyleSheet(
            "QPushButton { font-size: 13px; font-weight: bold; padding: 5px 12px;"
            " background: #7b1fa2; color: white; border: none; }"
            "QPushButton:hover { background: #6a1b9a; }"
            "QPushButton:pressed { background: #4a148c; }"
        )
        self.sacrifice_all_btn.clicked.connect(self._sacrifice_all_trash)

        self._scroll_area = QScrollArea()
        self._scroll_area.setWidgetResizable(True)
        self._scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        self.grid_container = QWidget()
        self.grid = QGridLayout(self.grid_container)
        self.grid.setSpacing(4)
        self.grid.setContentsMargins(8, 8, 8, 8)
        self.grid.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        self._scroll_area.setWidget(self.grid_container)

        left_layout.addWidget(self.tab_bar)
        left_layout.addWidget(sort_bar)

        # ── Multi-selection action bar ─────────────────────────────────
        self.multi_select_bar = QWidget()
        self.multi_select_bar.setVisible(False)
        self.multi_select_bar.setStyleSheet(
            "QWidget { background: #1a2d1a; border-bottom: 1px solid #3a5a3a; }"
        )
        ms_layout = QHBoxLayout(self.multi_select_bar)
        ms_layout.setContentsMargins(8, 4, 8, 4)
        ms_layout.setSpacing(6)

        self.multi_select_count_lbl = QLabel()
        self.multi_select_count_lbl.setStyleSheet("color: #88cc44; font-weight: bold; font-size: 12px;")
        ms_layout.addWidget(self.multi_select_count_lbl)
        ms_layout.addStretch()

        _ms_btn_style = (
            "QPushButton { font-size: 12px; font-weight: bold; padding: 3px 10px;"
            " border: none; border-radius: 3px; color: white; }"
        )
        ms_sacrifice_btn = QPushButton("✦ Sacrifice")
        ms_sacrifice_btn.setStyleSheet(_ms_btn_style + "QPushButton { background: #7b1fa2; }"
                                        "QPushButton:hover { background: #6a1b9a; }")
        ms_sacrifice_btn.clicked.connect(self._sacrifice_selected)
        ms_layout.addWidget(ms_sacrifice_btn)

        ms_trash_btn = QPushButton("🗑 Trash")
        ms_trash_btn.setStyleSheet(_ms_btn_style + "QPushButton { background: #555; }"
                                    "QPushButton:hover { background: #444; }")
        ms_trash_btn.clicked.connect(self._move_selected_to_trash)
        ms_layout.addWidget(ms_trash_btn)

        self.ms_gift_btn = QPushButton("🎁 Send Gift")
        self.ms_gift_btn.setStyleSheet(_ms_btn_style + "QPushButton { background: #6a3d9a; }"
                                        "QPushButton:hover { background: #5a2d8a; }")
        self.ms_gift_btn.setVisible(False)
        self.ms_gift_btn.clicked.connect(self._send_gift_selected)
        ms_layout.addWidget(self.ms_gift_btn)

        ms_clear_btn = QPushButton("✕")
        ms_clear_btn.setFixedWidth(28)
        ms_clear_btn.setStyleSheet(_ms_btn_style + "QPushButton { background: #333; }"
                                    "QPushButton:hover { background: #222; }")
        ms_clear_btn.clicked.connect(self._clear_multi_selection)
        ms_layout.addWidget(ms_clear_btn)

        left_layout.addWidget(self.multi_select_bar)
        left_layout.addWidget(self.sacrifice_all_btn)
        left_layout.addWidget(self._scroll_area)

        # ── Right: detail panel ───────────────────────────────────────
        detail_frame = QFrame()
        detail_frame.setMinimumWidth(260)
        detail_frame.setMaximumWidth(320)
        detail_layout = QVBoxLayout(detail_frame)
        detail_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        detail_layout.setSpacing(8)

        self.detail_icon = QLabel()
        self.detail_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.detail_icon.setFixedSize(96, 96)

        icon_wrapper = QWidget()
        iw_layout = QHBoxLayout(icon_wrapper)
        iw_layout.addStretch()
        iw_layout.addWidget(self.detail_icon)
        iw_layout.addStretch()

        self.detail_name = QLabel()
        self.detail_name.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.detail_name.setStyleSheet("font-size: 15px; font-weight: bold;")
        self.detail_name.setWordWrap(True)

        self.detail_info = QLabel()
        self.detail_info.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        self.detail_info.setWordWrap(True)
        self.detail_info.setTextFormat(Qt.TextFormat.RichText)

        self.sacrifice_btn = QPushButton("✦ Sacrifice")
        self.sacrifice_btn.setVisible(False)
        self.sacrifice_btn.setStyleSheet(
            "QPushButton { font-size: 13px; font-weight: bold; padding: 6px 12px;"
            " background: #7b1fa2; color: white; border: none; border-radius: 4px; }"
            "QPushButton:hover { background: #6a1b9a; }"
            "QPushButton:pressed { background: #4a148c; }"
        )
        self.sacrifice_btn.clicked.connect(self._sacrifice_item)

        self.repair_btn = QPushButton("🔧 Repair → Storage")
        self.repair_btn.setVisible(False)
        self.repair_btn.setStyleSheet(
            "QPushButton { font-size: 13px; font-weight: bold; padding: 6px 12px;"
            " background: #f57f17; color: white; border: none; border-radius: 4px; }"
            "QPushButton:hover { background: #e65100; }"
            "QPushButton:pressed { background: #bf360c; }"
        )
        self.repair_btn.clicked.connect(self._repair_item)

        self.clone_to_storage_btn = QPushButton("⧉ Clone to Storage")
        self.clone_to_storage_btn.setVisible(False)
        self.clone_to_storage_btn.setStyleSheet(
            "QPushButton { font-size: 13px; font-weight: bold; padding: 6px 12px;"
            " background: #1976d2; color: white; border: none; border-radius: 4px; }"
            "QPushButton:hover { background: #1565c0; }"
            "QPushButton:pressed { background: #0d47a1; }"
        )
        self.clone_to_storage_btn.clicked.connect(self._clone_to_storage)

        self.move_btn = QPushButton()
        self.move_btn.setVisible(False)
        self.move_btn.setStyleSheet(
            "QPushButton { font-size: 13px; font-weight: bold; padding: 6px 12px;"
            " background: #00695c; color: white; border: none; border-radius: 4px; }"
            "QPushButton:hover { background: #00564a; }"
            "QPushButton:pressed { background: #004d40; }"
        )
        self.move_btn.clicked.connect(self._move_item)

        self.send_gift_btn = QPushButton("🎁 Send Gift")
        self.send_gift_btn.setVisible(False)
        self.send_gift_btn.setStyleSheet(
            "QPushButton { font-size: 13px; font-weight: bold; padding: 6px 12px;"
            " background: #6a3d9a; color: white; border: none; border-radius: 4px; }"
            "QPushButton:hover { background: #5a2d8a; }"
            "QPushButton:pressed { background: #4a1d7a; }"
        )
        self.send_gift_btn.clicked.connect(self._send_gift)

        detail_layout.addWidget(icon_wrapper)
        detail_layout.addWidget(self.detail_name)
        detail_layout.addWidget(self.detail_info)
        detail_layout.addSpacing(8)
        detail_layout.addWidget(self.sacrifice_btn)
        detail_layout.addWidget(self.repair_btn)
        detail_layout.addWidget(self.move_btn)
        detail_layout.addWidget(self.send_gift_btn)
        detail_layout.addWidget(self.clone_to_storage_btn)
        detail_layout.addStretch()

        splitter.addWidget(left_widget)
        splitter.addWidget(detail_frame)
        splitter.setSizes([680, 280])

        self.setCentralWidget(splitter)

    # ------------------------------------------------------------------
    # Gold / token bar
    # ------------------------------------------------------------------

    def _build_gold_bar(self):
        bar = self.statusBar()
        bar.setSizeGripEnabled(False)
        bar.setStyleSheet(
            "QStatusBar { background: #f5e9c8; border-top: 1px solid #d4b97a; }"
        )

        # ── Reload button (left) ──────────────────────────────────────
        self.reload_btn = QToolButton()
        self.reload_btn.setText("↺ Reload")
        self._reload_btn_normal_style = (
            "QToolButton { font-size: 13px; font-weight: bold; padding: 2px 10px;"
            " border: 1px solid #d4b97a; border-radius: 4px; background: #eedfa0; }"
            "QToolButton:hover { background: #e8d080; }"
            "QToolButton:pressed { background: #d4b97a; }"
        )
        self._reload_btn_alert_style = (
            "QToolButton { font-size: 13px; font-weight: bold; padding: 2px 10px;"
            " border: 2px solid #e65100; border-radius: 4px; background: #ffe0b2; color: #bf360c; }"
            "QToolButton:hover { background: #ffcc80; }"
            "QToolButton:pressed { background: #ffb74d; }"
        )
        self.reload_btn.setStyleSheet(self._reload_btn_normal_style)
        self.reload_btn.clicked.connect(lambda: self._reload(show_overlay=False))
        bar.addWidget(self.reload_btn)

        self.save_date_label = QLabel(self.ctrl.get_save_date_str())
        self.save_date_label.setStyleSheet(
            "QLabel { color: #7a5000; font-size: 12px; padding: 0 8px; }"
        )
        bar.addWidget(self.save_date_label)

        # ── Poll timer: detect newer save ─────────────────────────────
        self._poll_timer = QTimer(self)
        self._poll_timer.setInterval(3000)
        self._poll_timer.timeout.connect(self._check_save_updated)
        self._poll_timer.start()

        shop_btn = QToolButton()
        shop_btn.setText("Token Shop")
        shop_btn.setStyleSheet(
            "QToolButton { font-size: 13px; font-weight: bold; padding: 2px 10px;"
            " border: 1px solid #d4b97a; border-radius: 4px; background: #eedfa0; }"
            "QToolButton:hover { background: #e8d080; }"
            "QToolButton:pressed { background: #d4b97a; }"
        )
        shop_btn.clicked.connect(self._open_token_shop)
        bar.addWidget(shop_btn)

        self.receive_gift_btn = QToolButton()
        self.receive_gift_btn.setText("📬 Receive Gift")
        self.receive_gift_btn.setStyleSheet(
            "QToolButton { font-size: 13px; font-weight: bold; padding: 2px 10px;"
            " border: 1px solid #9c6fca; border-radius: 4px; background: #e8d4f5; color: #4a1d7a; }"
            "QToolButton:hover { background: #d4bcea; }"
            "QToolButton:pressed { background: #c0a8e0; }"
        )
        self.receive_gift_btn.clicked.connect(self._receive_gifts)
        bar.addWidget(self.receive_gift_btn)

        # ── Right side: tokens + separator + gold ─────────────────────
        right_widget = QWidget()
        right_layout = QHBoxLayout(right_widget)
        right_layout.setContentsMargins(4, 2, 12, 2)
        right_layout.setSpacing(8)

        label_style = "QLabel { color: #7a5000; font-size: 13px; font-weight: bold; }"

        # Tokens (one per rarity)
        self.token_labels = {}
        for rarity in RARITIES:
            token_path = os.path.join(TOKENS_DIR, f"{rarity}.png")
            icon_lbl = QLabel()
            pixmap = QPixmap(token_path)
            if not pixmap.isNull():
                icon_lbl.setPixmap(
                    pixmap.scaled(18, 18, Qt.AspectRatioMode.KeepAspectRatio,
                                  Qt.TransformationMode.SmoothTransformation)
                )
            right_layout.addWidget(icon_lbl)

            count_lbl = QLabel(str(self.ctrl.tokens.get(rarity, 0)))
            count_lbl.setStyleSheet(label_style)
            right_layout.addWidget(count_lbl)
            self.token_labels[rarity] = count_lbl

        # Separator
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.VLine)
        sep.setStyleSheet("QFrame { color: #d4b97a; }")
        right_layout.addWidget(sep)

        # Gold
        money_lbl = QLabel()
        money_px = QPixmap(MONEY_ICON)
        if not money_px.isNull():
            money_lbl.setPixmap(
                money_px.scaled(20, 20, Qt.AspectRatioMode.KeepAspectRatio,
                                Qt.TransformationMode.SmoothTransformation)
            )
        right_layout.addWidget(money_lbl)

        self.gold_text_label = QLabel(f"{self.ctrl.golds:,} gold")
        self.gold_text_label.setStyleSheet(
            "QLabel { color: #7a5000; font-size: 14px; font-weight: bold; }"
        )
        right_layout.addWidget(self.gold_text_label)

        bar.addPermanentWidget(right_widget)

    # ------------------------------------------------------------------
    # Overlay — "go to main menu" screen
    # ------------------------------------------------------------------

    def _build_overlay(self):
        """Create the full-window overlay shown after every save load."""
        self._overlay = QWidget(self)
        self._overlay.setObjectName("overlay")
        self._overlay.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self._overlay.setStyleSheet(
            "QWidget#overlay { background: rgba(10, 10, 20, 200); }"
        )

        outer = QVBoxLayout(self._overlay)
        outer.setAlignment(Qt.AlignmentFlag.AlignCenter)

        card = QFrame()
        card.setStyleSheet(
            "QFrame { background: #1a1a2e; border: 2px solid #4a9eff;"
            " border-radius: 14px; }"
        )
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(40, 32, 40, 32)
        card_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        card_layout.setSpacing(16)

        icon_lbl = QLabel("💾")
        icon_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon_lbl.setStyleSheet(
            "QLabel { font-size: 52px; background: transparent; border: none; }"
        )

        msg_lbl = QLabel()
        msg_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        msg_lbl.setTextFormat(Qt.TextFormat.RichText)
        msg_lbl.setWordWrap(True)
        msg_lbl.setStyleSheet(
            "QLabel { color: #d0d8ff; font-size: 15px;"
            " background: transparent; border: none; }"
        )
        msg_lbl.setText(
            "<span style='font-size:20px; font-weight:bold; color:#4a9eff;'>"
            "Save file loaded</span><br><br>"
            "Please return to the <b>Main Menu</b> and click <b>Continue</b><br>"
            "to load the latest state, then come back here."
        )

        continue_btn = QPushButton("✓  I'm on the Main Menu — Continue")
        continue_btn.setFixedWidth(320)
        continue_btn.setStyleSheet(
            "QPushButton { font-size: 14px; font-weight: bold; padding: 12px 24px;"
            " background: #4a9eff; color: white; border: none; border-radius: 7px; }"
            "QPushButton:hover   { background: #3a8eef; }"
            "QPushButton:pressed { background: #2272cc; }"
        )
        continue_btn.clicked.connect(self._dismiss_overlay)

        card_layout.addWidget(icon_lbl)
        card_layout.addWidget(msg_lbl)
        card_layout.addSpacing(8)
        card_layout.addWidget(continue_btn, alignment=Qt.AlignmentFlag.AlignCenter)

        outer.addWidget(card)

        self._overlay.hide()
        self._overlay.raise_()

    def _show_overlay(self):
        """Resize and show the overlay on top of everything."""
        self._overlay.setGeometry(0, 0, self.width(), self.height())
        self._overlay.raise_()
        self._overlay.show()

    def _dismiss_overlay(self):
        """Hide the overlay so the user can interact with the app."""
        self._overlay.hide()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, "_overlay") and self._overlay.isVisible():
            self._overlay.setGeometry(0, 0, self.width(), self.height())

    # ------------------------------------------------------------------
    # Token Shop
    # ------------------------------------------------------------------

    def _open_token_shop(self):
        from ui.token_shop import TokenShopDialog
        self._poll_timer.stop()   # ignore our own writes during the shop session
        dialog = TokenShopDialog(
            self,
            tokens=self.ctrl.tokens,
            pool_items=self.ctrl.pool_items,
            items_pool=self.ctrl.items_pool,
            sav_path=self.sav_path,
            inventories=self.ctrl.inventories,
            loaded_mtime=self.ctrl.loaded_mtime,
            debug=DEBUG_MODE,
        )
        dialog.exec()
        self._reload()            # sync loaded_mtime to whatever the shop wrote
        self._poll_timer.start()  # resume external-change detection

    # ------------------------------------------------------------------
    # Save-change guard (UI dialog only)
    # ------------------------------------------------------------------

    def _confirm_if_save_changed(self) -> bool:
        """Show a confirmation dialog if the save file has been modified since last load.
        Returns True if it is safe to proceed with a write operation."""
        changed, _, date_str = self.ctrl.check_save_changed()
        if not changed:
            return True

        msg = QMessageBox(self)
        msg.setWindowTitle("⚠ Sauvegarde plus récente détectée")
        msg.setTextFormat(Qt.TextFormat.RichText)
        msg.setText(
            f"La sauvegarde a été modifiée depuis le dernier chargement.<br><br>"
            f"<b>Date du fichier :</b> {date_str}<br><br>"
            f"Continuer va <b>écraser</b> cette version plus récente.<br>"
            f"Il est recommandé de faire un <b>Reload</b> d'abord."
        )
        msg.setStandardButtons(QMessageBox.StandardButton.Ok | QMessageBox.StandardButton.Cancel)
        msg.setDefaultButton(QMessageBox.StandardButton.Cancel)
        msg.button(QMessageBox.StandardButton.Ok).setText("Écraser quand même")
        return msg.exec() == QMessageBox.StandardButton.Ok

    # ------------------------------------------------------------------
    # Poll for newer save / reload
    # ------------------------------------------------------------------

    def _check_save_updated(self):
        """Auto-reload when the save file changes on disk (external change = game saved)."""
        changed, _, _ = self.ctrl.check_save_changed()
        if changed:
            self._reload(show_overlay=True)

    def _reload(self, show_overlay: bool = False):
        current_tab = self._tab_key(self.tab_bar.tabText(self.tab_bar.currentIndex()))
        self.ctrl.load_data()
        self.reload_btn.setText("↺ Reload")
        self.reload_btn.setStyleSheet(self._reload_btn_normal_style)
        self.gold_text_label.setText(f"{self.ctrl.golds:,} gold")
        for rarity, lbl in self.token_labels.items():
            lbl.setText(str(self.ctrl.tokens.get(rarity, 0)))
        self.save_date_label.setText(self.ctrl.get_save_date_str())
        self._clear_grid()
        self._clear_detail()
        self._hide_all_action_btns()
        self._refresh_sacrifice_all_btn()
        self._refresh_pool_tab_title()
        self._populate(self.ctrl.inv_items[current_tab])
        if show_overlay:
            self._show_overlay()

    def _hide_all_action_btns(self):
        self.sacrifice_btn.setVisible(False)
        self.repair_btn.setVisible(False)
        self.move_btn.setVisible(False)
        self.send_gift_btn.setVisible(False)
        self.clone_to_storage_btn.setVisible(False)

    def _refresh_sacrifice_all_btn(self):
        current_tab = self._tab_key(self.tab_bar.tabText(self.tab_bar.currentIndex()))
        non_broken = [
            it for it in self.ctrl.inventories["trash"].items
            if not getattr(it, "broken", False)
        ]
        visible = current_tab == "Trash" and len(non_broken) > 0
        self.sacrifice_all_btn.setVisible(visible)

    def _tab_key(self, text: str) -> str:
        """Return the base key from a tab label, stripping any '  N/M' suffix."""
        return text.split("  ")[0]

    def _refresh_pool_tab_title(self):
        """Update the Pool tab label with discovered/total counts."""
        discovered = len(self.ctrl.pool_items)
        total = discovered + len(self.ctrl.undiscovered_pool_items)
        for i in range(self.tab_bar.count()):
            if self.tab_bar.tabText(i).startswith("Pool"):
                self.tab_bar.setTabText(i, f"Pool  {discovered}/{total}")
                break

    # ------------------------------------------------------------------
    # Tab switching
    # ------------------------------------------------------------------

    def _on_tab_changed(self, index: int):
        self._selected_item_idx = None
        self._selected_inv_key = None
        self._clear_grid()
        self._clear_detail()
        self._hide_all_action_btns()
        self._refresh_sacrifice_all_btn()
        self._refresh_multi_bar()
        label = self._tab_key(self.tab_bar.tabText(index))
        self._populate(self.ctrl.inv_items[label])

    def _clear_grid(self):
        self._selected_btn = None
        self._clear_multi_selection()
        while self.grid.count():
            item = self.grid.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

    def _clear_detail(self):
        self.detail_icon.clear()
        self.detail_name.clear()
        self.detail_info.clear()

    # ------------------------------------------------------------------
    # Sorting
    # ------------------------------------------------------------------

    def _set_sort(self, key: str):
        if key == self._sort_key:
            return
        self._sort_key = key
        base, active = self._sort_btn_styles
        for k, btn in self._sort_btns.items():
            btn.setStyleSheet(active if k == key else base)
        label = self._tab_key(self.tab_bar.tabText(self.tab_bar.currentIndex()))
        self._clear_grid()
        self._populate(self.ctrl.inv_items[label])

    def _sorted_indexed(self, indexed: list) -> list:
        if self._sort_key == "default":
            return indexed
        if self._sort_key == "name":
            return sorted(indexed, key=lambda t: (
                (t[1].details or {}).get("name_resolved") or t[1].name or ""
            ).lower())
        if self._sort_key == "rarity":
            return sorted(indexed, key=lambda t: (
                RARITY_ORDER.get(t[1].rarity, 99),
                ((t[1].details or {}).get("name_resolved") or t[1].name or "").lower()
            ))
        if self._sort_key == "category":
            return sorted(indexed, key=lambda t: (
                t[1].category or "zzz",
                ((t[1].details or {}).get("name_resolved") or t[1].name or "").lower()
            ))
        return indexed

    # ------------------------------------------------------------------
    # Data population (grid rendering)
    # ------------------------------------------------------------------

    def _make_item_btn(self, orig_idx: int, item, items) -> QToolButton:
        details   = item.details or {}
        icon_path = os.path.join(ICON_DIR, item.icon_name or "")
        pixmap    = svg_to_pixmap(icon_path, ICON_SIZE)
        if getattr(item, "broken", False):
            pixmap = broken_overlay_pixmap(pixmap)
        elif getattr(item, "locked", False):
            pixmap = locked_overlay_pixmap(pixmap)

        tooltip = details.get("name_resolved") or item.name or "?"
        if getattr(item, "broken", False):
            tooltip += " [BROKEN]"
        if getattr(item, "locked", False):
            tooltip += " [Not discovered]"

        rarity = details.get("rarity", "")
        bg     = RARITY_BG.get(rarity, "rgba(80, 80, 80, 0.20)")

        btn = QToolButton()
        btn.setIcon(QIcon(pixmap))
        btn.setIconSize(QSize(ICON_SIZE, ICON_SIZE))
        btn.setFixedSize(ICON_SIZE + 8, ICON_SIZE + 8)
        btn.setToolTip(tooltip)
        btn.setCheckable(True)
        btn.setProperty("item_rarity", rarity)
        btn.setStyleSheet(
            f"QToolButton {{ border: 2px solid transparent; border-radius: 4px; background: {bg}; }}"
            "QToolButton:checked { border: 2px solid #4a9eff; }"
            "QToolButton:hover   { border: 2px solid rgba(255,255,255,0.4); }"
        )
        btn.clicked.connect(
            lambda checked, i=orig_idx, b=btn, it=items: self._on_select(
                i, b, it,
                multi=bool(QApplication.keyboardModifiers() & Qt.KeyboardModifier.ControlModifier)
            )
        )
        return btn

    def _populate(self, items):
        indexed = [
            (i, item) for i, item in enumerate(items)
            if (item.details or {}).get("rarity") not in EXCLUDED_RARITIES
        ]

        discovered = self._sorted_indexed(
            [(i, it) for i, it in indexed if not getattr(it, "locked", False)]
        )
        locked = self._sorted_indexed(
            [(i, it) for i, it in indexed if getattr(it, "locked", False)]
        )

        if self._sort_key == "category":
            next_row = self._populate_grouped(discovered, items, start_row=0)
        else:
            next_row = self._populate_flat(discovered, items, start_row=0)

        if locked:
            # ── "Not yet discovered" separator ───────────────────────
            sep = QLabel("  Not yet discovered")
            sep.setFixedHeight(24)
            sep.setStyleSheet(
                "QLabel { font-size: 11px; font-weight: bold; color: #666;"
                " background: rgba(255,255,255,0.03);"
                " border-top: 1px solid #333; border-bottom: 1px solid #333;"
                " padding-left: 4px; }"
            )
            self.grid.addWidget(sep, next_row, 0, 1, GRID_COLS)
            next_row += 1

            # ── Virtual scroll grid for undiscovered items ────────────
            vgrid = VirtualItemGrid(locked, items, self._make_item_btn)
            self.grid.addWidget(vgrid, next_row, 0, 1, GRID_COLS)
            vgrid.attach(self._scroll_area)

    def _populate_flat(self, indexed: list, items, start_row: int = 0) -> int:
        """Simple flat grid. Returns the next available grid row."""
        for grid_pos, (orig_idx, item) in enumerate(indexed):
            row = start_row + grid_pos // GRID_COLS
            col = grid_pos % GRID_COLS
            self.grid.addWidget(self._make_item_btn(orig_idx, item, items), row, col)
        if not indexed:
            return start_row
        last_pos = len(indexed) - 1
        last_row = start_row + last_pos // GRID_COLS
        return last_row + 1  # next empty row

    def _populate_grouped(self, indexed: list, items, start_row: int = 0) -> int:
        """Grid with a spanning category header before each group. Returns next row."""
        groups: dict[str, list] = {}
        for orig_idx, item in indexed:
            cat = item.category or "Unknown"
            groups.setdefault(cat, []).append((orig_idx, item))

        grid_row = start_row
        for cat, group in groups.items():
            header = QLabel(f"  {cat.capitalize()}")
            header.setFixedHeight(24)
            header.setStyleSheet(
                "QLabel { font-size: 11px; font-weight: bold; color: #aaaaaa;"
                " background: rgba(255,255,255,0.05);"
                " border-bottom: 1px solid #444; padding-left: 4px; }"
            )
            self.grid.addWidget(header, grid_row, 0, 1, GRID_COLS)
            grid_row += 1

            for col, (orig_idx, item) in enumerate(group):
                self.grid.addWidget(
                    self._make_item_btn(orig_idx, item, items),
                    grid_row,
                    col % GRID_COLS,
                )
                if (col + 1) % GRID_COLS == 0:
                    grid_row += 1

            if len(group) % GRID_COLS != 0:
                grid_row += 1

        return grid_row

    # ------------------------------------------------------------------
    # Multi-selection helpers
    # ------------------------------------------------------------------

    def _btn_multi_style(self, btn: QToolButton, selected: bool):
        rarity = btn.property("item_rarity") or ""
        bg = RARITY_BG.get(rarity, "rgba(80, 80, 80, 0.20)")
        if selected:
            btn.setStyleSheet(
                f"QToolButton {{ border: 3px solid #44ff44; border-radius: 4px; background: {bg}; }}"
                "QToolButton:checked { border: 3px solid #44ff44; }"
                "QToolButton:hover   { border: 3px solid #88ff88; }"
            )
        else:
            btn.setStyleSheet(
                f"QToolButton {{ border: 2px solid transparent; border-radius: 4px; background: {bg}; }}"
                "QToolButton:checked { border: 2px solid #4a9eff; }"
                "QToolButton:hover   { border: 2px solid rgba(255,255,255,0.4); }"
            )

    def _refresh_multi_bar(self):
        n          = len(self._multi_selection)
        in_storage = self._tab_key(self.tab_bar.tabText(self.tab_bar.currentIndex())) == "Storage"
        visible    = n > 0 and in_storage
        self.multi_select_bar.setVisible(visible)
        if visible:
            self.multi_select_count_lbl.setText(
                f"{n} item{'s' if n != 1 else ''} selected  (Ctrl+click to add/remove)"
            )
            # Show gift button only when gift is configured
            try:
                ctx = self.ctrl.get_gift_context()
                if ctx.get("is_known_user"):
                    self.ms_gift_btn.setText(f"🎁 Send to {ctx['recipient_name']}")
                    self.ms_gift_btn.setVisible(True)
                else:
                    self.ms_gift_btn.setVisible(False)
            except Exception:
                self.ms_gift_btn.setVisible(False)

    def _clear_multi_selection(self):
        for btn in self._multi_selection.values():
            self._btn_multi_style(btn, selected=False)
            btn.setChecked(False)
        self._multi_selection.clear()
        self._refresh_multi_bar()

    # ------------------------------------------------------------------
    # Item selection → detail panel
    # ------------------------------------------------------------------

    def _on_select(self, idx: int, btn: QToolButton, items, multi: bool = False):
        current_tab = self._tab_key(self.tab_bar.tabText(self.tab_bar.currentIndex()))

        # ── Ctrl+Click in Storage → toggle multi-selection ────────────
        if multi and current_tab == "Storage":
            if getattr(items[idx], "locked", False):
                return
            if idx in self._multi_selection:
                self._btn_multi_style(btn, selected=False)
                btn.setChecked(False)
                del self._multi_selection[idx]
            else:
                if self._selected_btn and self._selected_btn is not btn:
                    self._selected_btn.setChecked(False)
                self._selected_btn = None
                self._selected_item_idx = None
                self._btn_multi_style(btn, selected=True)
                btn.setChecked(True)
                self._multi_selection[idx] = btn
            self._refresh_multi_bar()
            n = len(self._multi_selection)
            if n == 0:
                self._clear_detail()
                self._hide_all_action_btns()
            else:
                self.detail_icon.clear()
                self.detail_name.setText(f"{n} item{'s' if n != 1 else ''} selected")
                self.detail_info.setText(
                    '<span style="color:#888">Use the bar above to sacrifice<br>or move to trash.</span>'
                )
                self._hide_all_action_btns()
            return

        # ── Regular click → single-select ─────────────────────────────
        self._clear_multi_selection()
        if self._selected_btn and self._selected_btn is not btn:
            self._selected_btn.setChecked(False)
        self._selected_btn = btn
        self._selected_item_idx = idx
        self._selected_inv_key = current_tab

        item    = items[idx]
        details = item.details or {}

        # Large icon
        icon_path = os.path.join(ICON_DIR, item.icon_name or "")
        detail_px = svg_to_pixmap(icon_path, 96)
        if getattr(item, "locked", False):
            detail_px = locked_overlay_pixmap(detail_px)
        self.detail_icon.setPixmap(detail_px)

        # Name
        self.detail_name.setText(details.get("name_resolved") or item.name or "?")

        # Info block
        lines = []
        if getattr(item, "broken", False):
            lines.append('<b><span style="color:#e02828">⚠ BROKEN</span></b>')
        rarity = item.rarity
        if rarity:
            color = RARITY_COLORS.get(rarity, "#cccccc")
            lines.append(f'<b>Rarity:</b> <span style="color:{color}">{rarity.capitalize()}</span>')
        cat = item.category or ("quest" if item.is_quest_item else "—")
        lines.append(f"<b>Category:</b> {cat}")
        if item.charges != -1:
            lines.append(f"<b>Charges:</b> {item.charges}")
        if item.subname:
            lines.append(f"<b>Subname:</b> {item.subname}")
        desc = details.get("desc_resolved")
        if desc:
            lines.append(f"<br><i>{desc}</i>")
        self.detail_info.setText("<br>".join(lines))

        is_pool_tab = current_tab == "Pool"
        is_broken   = getattr(item, "broken", False)
        is_locked   = getattr(item, "locked", False)

        if is_locked or is_pool_tab:
            self.sacrifice_btn.setVisible(False)
            self.repair_btn.setVisible(False)
            self.move_btn.setVisible(False)
            self.send_gift_btn.setVisible(False)
            self.clone_to_storage_btn.setVisible(
                DEBUG_MODE and is_pool_tab and not is_locked
            )
        else:
            self.clone_to_storage_btn.setVisible(False)
            token_label = (
                rarity.replace("_", " ").capitalize()
                if rarity in self.ctrl.tokens else "?"
            )
            self.sacrifice_btn.setText(f"✦ Sacrifice → {token_label} token")
            self.sacrifice_btn.setVisible(not is_broken)
            self.repair_btn.setVisible(is_broken and current_tab == "Trash")
            if not is_broken:
                self.move_btn.setText(
                    "🗑 Move to Trash" if current_tab == "Storage" else "📦 Move to Storage"
                )
            self.move_btn.setVisible(not is_broken)

            # Gift button — only for storage items that aren't broken
            ctx = self.ctrl.get_gift_context()
            if ctx["is_known_user"] and current_tab == "Storage" and not is_broken:
                self.send_gift_btn.setText(f"🎁 Send to {ctx['recipient_name']}")
                self.send_gift_btn.setVisible(True)
            else:
                self.send_gift_btn.setVisible(False)

    # ------------------------------------------------------------------
    # Multi-selection actions
    # ------------------------------------------------------------------

    def _sacrifice_selected(self):
        if not self._multi_selection:
            return
        if not self._confirm_if_save_changed():
            return
        indices = sorted(self._multi_selection.keys())
        gains   = self.ctrl.get_sacrifice_multiple_gains(indices)
        if not gains:
            return

        lines = [
            f'<span style="color:{RARITY_COLORS.get(r, "#cccccc")}">'
            f'<b>{count}× {r.replace("_"," ").capitalize()} token</b></span>'
            for r, count in gains.items()
        ]
        msg = QMessageBox(self)
        msg.setWindowTitle("Sacrifice la sélection")
        msg.setTextFormat(Qt.TextFormat.RichText)
        msg.setText(
            f"Sacrifier <b>{len(indices)} item(s)</b> ?<br><br>"
            f"Vous allez gagner :<br>" + "<br>".join(lines)
        )
        msg.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel)
        msg.setDefaultButton(QMessageBox.StandardButton.Cancel)
        if msg.exec() != QMessageBox.StandardButton.Yes:
            return

        self.ctrl.apply_sacrifice_multiple(indices)
        self._sync_token_labels()
        self._clear_multi_selection()
        self._clear_grid()
        self._clear_detail()
        self._hide_all_action_btns()
        self._populate(self.ctrl.inv_items["Storage"])

    def _move_selected_to_trash(self):
        if not self._multi_selection:
            return
        if not self._confirm_if_save_changed():
            return
        indices = sorted(self._multi_selection.keys(), reverse=True)
        msg = QMessageBox(self)
        msg.setWindowTitle("Déplacer vers Trash")
        msg.setText(f"Déplacer <b>{len(indices)} item(s)</b> vers le Trash ?")
        msg.setTextFormat(Qt.TextFormat.RichText)
        msg.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel)
        msg.setDefaultButton(QMessageBox.StandardButton.Cancel)
        if msg.exec() != QMessageBox.StandardButton.Yes:
            return
        self.ctrl.apply_move_multiple_to_trash(indices)
        self._clear_multi_selection()
        self._clear_grid()
        self._clear_detail()
        self._hide_all_action_btns()
        self._refresh_sacrifice_all_btn()
        self._populate(self.ctrl.inv_items["Storage"])

    def _send_gift_selected(self):
        if not self._multi_selection:
            return
        if not self._confirm_if_save_changed():
            return

        ctx = self.ctrl.get_gift_context()
        if not ctx.get("is_known_user"):
            QMessageBox.warning(self, "Erreur", "Impossible de déterminer le destinataire du cadeau.")
            return

        indices    = sorted(self._multi_selection.keys())
        storage    = self.ctrl.inventories["storage"]
        item_names = [
            ((storage.items[i].details or {}).get("name_resolved") or storage.items[i].name or "?")
            for i in indices
        ]
        items_html = "<br>".join(f"• {n}" for n in item_names)

        msg = QMessageBox(self)
        msg.setWindowTitle("🎁 Envoyer des cadeaux")
        msg.setTextFormat(Qt.TextFormat.RichText)
        msg.setText(
            f"Envoyer <b>{len(indices)} item(s)</b> à "
            f"<b>{ctx['recipient_name']}</b> ?<br><br>"
            f"{items_html}<br><br>"
            "Ces objets seront retirés de votre inventaire."
        )
        msg.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel)
        msg.setDefaultButton(QMessageBox.StandardButton.Cancel)
        if msg.exec() != QMessageBox.StandardButton.Yes:
            return

        try:
            count = self.ctrl.apply_send_gift_multiple(indices)
        except Exception as exc:
            QMessageBox.critical(self, "Erreur", f"Impossible d'envoyer les cadeaux :\n{exc}")
            return

        self._clear_multi_selection()
        self._clear_grid()
        self._clear_detail()
        self._hide_all_action_btns()
        self._populate(self.ctrl.inv_items["Storage"])
        QMessageBox.information(
            self, "Cadeaux envoyés",
            f"<b>{count}</b> objet(s) envoyé(s) à {ctx['recipient_name']} !"
        )

    # ------------------------------------------------------------------
    # Single-item actions
    # ------------------------------------------------------------------

    def _sacrifice_item(self):
        if self._selected_item_idx is None or self._selected_inv_key is None:
            return
        if not self._confirm_if_save_changed():
            return
        inv_key    = TAB_TO_INV_KEY[self._selected_inv_key]
        origin_tab = self._selected_inv_key
        self.ctrl.apply_sacrifice_item(inv_key, self._selected_item_idx)
        self._sync_token_labels()
        self._selected_item_idx = None
        self._selected_btn = None
        self._clear_grid()
        self._clear_detail()
        self._hide_all_action_btns()
        self._populate(self.ctrl.inv_items[origin_tab])

    def _move_item(self):
        if self._selected_item_idx is None or self._selected_inv_key is None:
            return
        if not self._confirm_if_save_changed():
            return
        src_key    = TAB_TO_INV_KEY[self._selected_inv_key]
        origin_tab = self._selected_inv_key
        self.ctrl.apply_move_item(src_key, self._selected_item_idx)
        self._selected_item_idx = None
        self._selected_btn = None
        self._clear_grid()
        self._clear_detail()
        self._hide_all_action_btns()
        self._refresh_sacrifice_all_btn()
        self._populate(self.ctrl.inv_items[origin_tab])

    def _sacrifice_all_trash(self):
        if not self._confirm_if_save_changed():
            return
        gains = self.ctrl.get_sacrifice_all_trash_gains()
        if not gains:
            return

        lines = [
            f'<span style="color:{RARITY_COLORS.get(r, "#cccccc")}">'
            f'<b>{count}× {r.replace("_"," ").capitalize()} token</b></span>'
            for r, count in gains.items()
        ]
        msg = QMessageBox(self)
        msg.setWindowTitle("Sacrifice All")
        msg.setTextFormat(Qt.TextFormat.RichText)
        msg.setText(
            "Voulez-vous vraiment sacrifier tous les objets non-brisés du Trash ?<br><br>"
            "Vous allez gagner :<br>" + "<br>".join(lines)
        )
        msg.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel)
        msg.setDefaultButton(QMessageBox.StandardButton.Cancel)
        if msg.exec() != QMessageBox.StandardButton.Yes:
            return

        self.ctrl.apply_sacrifice_all_trash()
        self._sync_token_labels()
        self._selected_item_idx = None
        self._selected_btn = None
        self._clear_grid()
        self._clear_detail()
        self._hide_all_action_btns()
        self._refresh_sacrifice_all_btn()
        self._populate(self.ctrl.inv_items["Trash"])

    def _repair_item(self):
        if self._selected_item_idx is None or self._selected_inv_key != "Trash":
            return
        if not self._confirm_if_save_changed():
            return

        info         = self.ctrl.get_repair_info(self._selected_item_idx)
        rarity       = info["rarity"]
        color        = RARITY_COLORS.get(rarity, "#cccccc")
        rarity_label = rarity.replace("_", " ").capitalize()

        if not info["can_afford"]:
            msg = QMessageBox(self)
            msg.setWindowTitle("Réparation impossible")
            msg.setTextFormat(Qt.TextFormat.RichText)
            msg.setText(
                f"Pas assez de tokens pour réparer cet objet.<br><br>"
                f'Coût : <span style="color:{color}"><b>{info["cost"]}× {rarity_label} token</b></span><br>'
                f'Disponible : <span style="color:{color}"><b>{info["available"]}</b></span>'
            )
            msg.setStandardButtons(QMessageBox.StandardButton.Ok)
            msg.exec()
            return

        msg = QMessageBox(self)
        msg.setWindowTitle("Réparer l'objet")
        msg.setTextFormat(Qt.TextFormat.RichText)
        msg.setText(
            f'Réparer <b>{info["display_name"]}</b> et le déplacer vers le Storage ?<br><br>'
            f'Coût : <span style="color:{color}"><b>{info["cost"]}× {rarity_label} token</b></span>'
            f' (vous en avez <b>{info["available"]}</b>)'
        )
        msg.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel)
        msg.setDefaultButton(QMessageBox.StandardButton.Cancel)
        if msg.exec() != QMessageBox.StandardButton.Yes:
            return

        self.ctrl.apply_repair_item(self._selected_item_idx)
        self._sync_token_labels()
        self._selected_item_idx = None
        self._selected_btn = None
        self._clear_grid()
        self._clear_detail()
        self._hide_all_action_btns()
        self._refresh_sacrifice_all_btn()
        self._populate(self.ctrl.inv_items["Trash"])

    def _clone_to_storage(self):
        if self._selected_item_idx is None:
            return
        if not self._confirm_if_save_changed():
            return
        self.ctrl.apply_clone_to_storage(self._selected_item_idx)

    def _send_gift(self):
        if self._selected_item_idx is None or self._selected_inv_key != "Storage":
            return
        if not self._confirm_if_save_changed():
            return

        ctx  = self.ctrl.get_gift_context()
        item = self.ctrl.inventories["storage"].items[self._selected_item_idx]
        name = (item.details or {}).get("name_resolved") or item.name or "?"

        msg = QMessageBox(self)
        msg.setWindowTitle("🎁 Envoyer un cadeau")
        msg.setTextFormat(Qt.TextFormat.RichText)
        msg.setText(
            f"Envoyer <b>{name}</b> à <b>{ctx['recipient_name']}</b> ?<br><br>"
            f"L'objet sera retiré de votre inventaire."
        )
        msg.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel)
        msg.setDefaultButton(QMessageBox.StandardButton.Cancel)
        if msg.exec() != QMessageBox.StandardButton.Yes:
            return

        try:
            self.ctrl.apply_send_gift("storage", self._selected_item_idx)
        except Exception as exc:
            QMessageBox.critical(self, "Erreur", f"Impossible d'envoyer le cadeau :\n{exc}")
            return

        self._selected_item_idx = None
        self._selected_btn = None
        self._clear_grid()
        self._clear_detail()
        self._hide_all_action_btns()
        self._populate(self.ctrl.inv_items["Storage"])
        QMessageBox.information(self, "Cadeau envoyé", f"<b>{name}</b> envoyé à {ctx['recipient_name']} !")

    def _receive_gifts(self):
        if not self._confirm_if_save_changed():
            return

        try:
            received = self.ctrl.apply_receive_gifts()
        except Exception as exc:
            QMessageBox.critical(self, "Erreur", f"Impossible de recevoir les cadeaux :\n{exc}")
            return

        if not received:
            QMessageBox.information(self, "Receive Gift", "Aucun cadeau en attente.")
            return

        # Refresh storage tab
        current_tab = self._tab_key(self.tab_bar.tabText(self.tab_bar.currentIndex()))
        if current_tab == "Storage":
            self._clear_grid()
            self._clear_detail()
            self._hide_all_action_btns()
            self._populate(self.ctrl.inv_items["Storage"])
        # Also keep inv_items in sync for other tabs
        self.ctrl.inv_items["Storage"] = self.ctrl.inventories["storage"].items
        # Refresh pool tab title in case new items were discovered via the gift
        self._refresh_pool_tab_title()

        names = [
            (r.get("name") or "?") for r in received
        ]
        items_html = "<br>".join(f"• {n}" for n in names)
        QMessageBox.information(
            self, "Cadeaux reçus !",
            f"<b>{len(received)}</b> objet(s) ajouté(s) au Storage :<br><br>{items_html}"
        )

    # ------------------------------------------------------------------
    # UI helpers
    # ------------------------------------------------------------------

    def _sync_token_labels(self):
        """Refresh all token count labels from controller state."""
        for rarity, lbl in self.token_labels.items():
            lbl.setText(str(self.ctrl.tokens.get(rarity, 0)))
