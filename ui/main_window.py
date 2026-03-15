import os

from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QPixmap, QPainter, QIcon
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QHBoxLayout, QVBoxLayout,
    QLabel, QFrame, QSplitter,
    QScrollArea, QGridLayout, QToolButton, QTabBar, QPushButton,
)

from parse.item import Item
from utils.loaders import load_inventories, load_gold
from utils.savers import save_inventories, save_gold

# mapping tab label → save_inventories key
TAB_TO_INV_KEY = {"Storage": "storage", "Trash": "trash"}

ICON_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "assets", "img")
MONEY_ICON = os.path.join(os.path.dirname(os.path.dirname(__file__)), "assets", "icons", "money.png")
GRID_COLS = 7
ICON_SIZE = 56
EXCLUDED_RARITIES = {"sidequest", "quest"}

RARITY_COLORS = {
    "common":    "#aaaaaa",
    "uncommon":  "#55aa55",
    "rare":      "#5588ff",
    "very_rare": "#ffaa00",
}
RARITY_BG = {
    "common":    "rgba(150, 150, 150, 0.30)",
    "uncommon":  "rgba(85,  170,  85, 0.30)",
    "rare":      "rgba(85,  136, 255, 0.30)",
    "very_rare": "rgba(255, 170,   0, 0.35)",
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


class MainWindow(QMainWindow):
    def __init__(self, sav_path: str):
        super().__init__()
        self.setWindowTitle("Mewgenics Storage QOL")
        self.resize(960, 640)

        self.sav_path = sav_path
        self._selected_item_idx: int | None = None
        self._selected_inv_key: str | None = None
        self._selected_btn: QToolButton | None = None

        self._load_data()
        self._build_ui()
        self._build_gold_bar()
        self._populate(self.inv_items["Storage"])

    # ------------------------------------------------------------------
    # Data loading
    # ------------------------------------------------------------------

    def _load_data(self):
        raw = load_inventories(self.sav_path)
        self.inventories = {
            "storage": raw["storage"],
            "backpack": raw["backpack"],
            "trash":    raw["trash"],
        }
        self.golds = load_gold(self.sav_path)
        self.inv_items = {
            "Storage": self.inventories["storage"].items,
            "Trash":   self.inventories["trash"].items,
        }

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
        for label in self.inv_items:
            self.tab_bar.addTab(label)
        self.tab_bar.currentChanged.connect(self._on_tab_changed)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        self.grid_container = QWidget()
        self.grid = QGridLayout(self.grid_container)
        self.grid.setSpacing(4)
        self.grid.setContentsMargins(8, 8, 8, 8)
        self.grid.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        scroll.setWidget(self.grid_container)

        left_layout.addWidget(self.tab_bar)
        left_layout.addWidget(scroll)

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

        self.sell_btn = QPushButton()
        self.sell_btn.setVisible(False)
        self.sell_btn.setStyleSheet(
            "QPushButton { font-size: 13px; font-weight: bold; padding: 6px 12px;"
            " background: #4caf50; color: white; border: none; border-radius: 4px; }"
            "QPushButton:hover { background: #43a047; }"
            "QPushButton:pressed { background: #388e3c; }"
        )
        self.sell_btn.clicked.connect(self._sell_item)

        self.duplicate_btn = QPushButton("⧉ Duplicate")
        self.duplicate_btn.setVisible(False)
        self.duplicate_btn.setStyleSheet(
            "QPushButton { font-size: 13px; font-weight: bold; padding: 6px 12px;"
            " background: #1976d2; color: white; border: none; border-radius: 4px; }"
            "QPushButton:hover { background: #1565c0; }"
            "QPushButton:pressed { background: #0d47a1; }"
        )
        self.duplicate_btn.clicked.connect(self._duplicate_item)

        action_row = QWidget()
        action_layout = QHBoxLayout(action_row)
        action_layout.setContentsMargins(0, 0, 0, 0)
        action_layout.setSpacing(6)
        action_layout.addWidget(self.sell_btn)
        action_layout.addWidget(self.duplicate_btn)

        detail_layout.addWidget(icon_wrapper)
        detail_layout.addWidget(self.detail_name)
        detail_layout.addWidget(self.detail_info)
        detail_layout.addSpacing(8)
        detail_layout.addWidget(action_row)
        detail_layout.addStretch()

        splitter.addWidget(left_widget)
        splitter.addWidget(detail_frame)
        splitter.setSizes([680, 280])

        self.setCentralWidget(splitter)

    # ------------------------------------------------------------------
    # Gold bar
    # ------------------------------------------------------------------

    def _build_gold_bar(self):
        bar = self.statusBar()
        bar.setSizeGripEnabled(False)
        bar.setStyleSheet(
            "QStatusBar { background: #f5e9c8; border-top: 1px solid #d4b97a; }"
        )

        # Reload button (left side)
        reload_btn = QToolButton()
        reload_btn.setText("↺ Reload")
        reload_btn.setStyleSheet(
            "QToolButton { font-size: 13px; font-weight: bold; padding: 2px 10px;"
            " border: 1px solid #d4b97a; border-radius: 4px; background: #eedfa0; }"
            "QToolButton:hover { background: #e8d080; }"
            "QToolButton:pressed { background: #d4b97a; }"
        )
        reload_btn.clicked.connect(self._reload)
        bar.addWidget(reload_btn)

        # Gold display (right side)
        gold_widget = QWidget()
        gold_layout = QHBoxLayout(gold_widget)
        gold_layout.setContentsMargins(8, 2, 12, 2)
        gold_layout.setSpacing(6)

        icon_lbl = QLabel()
        pixmap = QPixmap(MONEY_ICON)
        if not pixmap.isNull():
            icon_lbl.setPixmap(pixmap.scaled(20, 20, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
        gold_layout.addWidget(icon_lbl)

        self.gold_text_label = QLabel(f"{self.golds:,} gold")
        self.gold_text_label.setStyleSheet(
            "QLabel { color: #7a5000; font-size: 14px; font-weight: bold; }"
        )
        gold_layout.addWidget(self.gold_text_label)

        bar.addPermanentWidget(gold_widget)

    # ------------------------------------------------------------------
    # Reload
    # ------------------------------------------------------------------

    def _reload(self):
        current_tab = self.tab_bar.tabText(self.tab_bar.currentIndex())
        self._load_data()
        self.gold_text_label.setText(f"{self.golds:,} gold")
        self._clear_grid()
        self._clear_detail()
        self.sell_btn.setVisible(False)
        self.duplicate_btn.setVisible(False)
        self._populate(self.inv_items[current_tab])

    # ------------------------------------------------------------------
    # Sell
    # ------------------------------------------------------------------

    def _sell_item(self):
        if self._selected_item_idx is None or self._selected_inv_key is None:
            return

        inv_key = TAB_TO_INV_KEY[self._selected_inv_key]
        inventory = self.inventories[inv_key]
        item = inventory.items[self._selected_item_idx]

        price = int(item.price) if item.price else 0
        self.golds += price
        self.gold_text_label.setText(f"{self.golds:,} gold")

        del inventory.raws[self._selected_item_idx]
        del inventory.items[self._selected_item_idx]
        inventory.count -= 1

        save_inventories(self.sav_path, self.inventories)
        save_gold(self.sav_path, self.golds)

        self._selected_item_idx = None
        self._selected_btn = None
        self._clear_grid()
        self._clear_detail()
        self.sell_btn.setVisible(False)
        self.duplicate_btn.setVisible(False)
        self._populate(self.inv_items[self._selected_inv_key])

    # ------------------------------------------------------------------
    # Tab switching
    # ------------------------------------------------------------------

    def _on_tab_changed(self, index: int):
        label = self.tab_bar.tabText(index)
        self._selected_item_idx = None
        self._selected_inv_key = None
        self._clear_grid()
        self._clear_detail()
        self.sell_btn.setVisible(False)
        self.duplicate_btn.setVisible(False)
        self._populate(self.inv_items[label])

    def _clear_grid(self):
        self._selected_btn = None
        while self.grid.count():
            item = self.grid.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

    def _clear_detail(self):
        self.detail_icon.clear()
        self.detail_name.clear()
        self.detail_info.clear()

    # ------------------------------------------------------------------
    # Data population
    # ------------------------------------------------------------------

    def _populate(self, items):
        grid_pos = 0
        for idx, item in enumerate(items):
            details = item.details or {}
            if details.get("rarity") in EXCLUDED_RARITIES:
                continue

            row, col = divmod(grid_pos, GRID_COLS)
            grid_pos += 1

            icon_path = os.path.join(ICON_DIR, item.icon_name or "")
            pixmap = svg_to_pixmap(icon_path, ICON_SIZE)

            tooltip = details.get("name_resolved") or item.name or "?"

            btn = QToolButton()
            btn.setIcon(QIcon(pixmap))
            btn.setIconSize(QSize(ICON_SIZE, ICON_SIZE))
            btn.setFixedSize(ICON_SIZE + 8, ICON_SIZE + 8)
            btn.setToolTip(tooltip)
            btn.setCheckable(True)
            rarity = details.get("rarity", "")
            bg = RARITY_BG.get(rarity, "rgba(80, 80, 80, 0.20)")
            btn.setStyleSheet(
                f"QToolButton {{ border: 2px solid transparent; border-radius: 4px; background: {bg}; }}"
                "QToolButton:checked { border: 2px solid #4a9eff; }"
                "QToolButton:hover { border: 2px solid rgba(255,255,255,0.4); }"
            )
            btn.clicked.connect(lambda checked, i=idx, b=btn, it=items: self._on_select(i, b, it))

            self.grid.addWidget(btn, row, col)

    # ------------------------------------------------------------------
    # Selection
    # ------------------------------------------------------------------

    def _on_select(self, idx: int, btn: QToolButton, items):
        if self._selected_btn and self._selected_btn is not btn:
            self._selected_btn.setChecked(False)
        self._selected_btn = btn
        self._selected_item_idx = idx
        self._selected_inv_key = self.tab_bar.tabText(self.tab_bar.currentIndex())

        item = items[idx]
        details = item.details or {}

        # Large icon
        icon_path = os.path.join(ICON_DIR, item.icon_name or "")
        self.detail_icon.setPixmap(svg_to_pixmap(icon_path, 96))

        # Name
        display_name = details.get("name_resolved") or item.name or "?"
        self.detail_name.setText(display_name)

        # Info block
        lines = []
        rarity = details.get("rarity")
        if rarity:
            color = RARITY_COLORS.get(rarity, "#cccccc")
            lines.append(f'<b>Rarity:</b> <span style="color:{color}">{rarity.capitalize()}</span>')

        cat = item.category or ("quest" if item.is_quest_item else "—")
        lines.append(f"<b>Category:</b> {cat}")
        lines.append(f"<b>Charges:</b> {item.charges}")

        price = int(item.price) if item.price else 0
        lines.append(f"<b>Price:</b> {price}")

        if item.subname:
            lines.append(f"<b>Subname:</b> {item.subname}")

        desc = details.get("desc_resolved")
        if desc:
            lines.append(f"<br><i>{desc}</i>")

        self.detail_info.setText("<br>".join(lines))

        self.sell_btn.setText(f"Sell for {price} gold")
        self.sell_btn.setVisible(True)
        self.duplicate_btn.setVisible(True)

    # ------------------------------------------------------------------
    # Duplicate
    # ------------------------------------------------------------------

    def _duplicate_item(self):
        if self._selected_item_idx is None or self._selected_inv_key is None:
            return

        inv_key = TAB_TO_INV_KEY[self._selected_inv_key]
        inventory = self.inventories[inv_key]

        original_raw = inventory.raws[self._selected_item_idx]
        new_seq_id = max((r.get("seqId", 0) for r in inventory.raws), default=0) + 1
        new_raw = {**original_raw, "seqId": new_seq_id}

        inventory.raws.append(new_raw)
        inventory.items.append(Item(new_raw))
        inventory.count += 1

        save_inventories(self.sav_path, self.inventories)

        self._clear_grid()
        self._populate(self.inv_items[self._selected_inv_key])
