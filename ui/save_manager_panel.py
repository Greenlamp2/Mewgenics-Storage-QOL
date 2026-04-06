"""
ui/save_manager_panel.py — Save Manager panel integrated into Mewgenics Storage QOL.

Features:
 - Named backups & Quick Save / Quick Load
 - Reload / Rename / Export / Clean backups
 - Safety backup before every restore
 - Sound Manager (random fart/burp, classic save/load, custom per-action)
 - Global keyboard shortcuts F7 (quick save) / F9 (quick load) via the `keyboard` lib
 - Sound config persisted in CUSTOM_FOLDER/save_manager_config.json
"""

from __future__ import annotations

import json
import os
import random
import shutil
from datetime import datetime

from PySide6.QtCore import Qt, QUrl, Signal
from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput
from PySide6.QtWidgets import (
    QButtonGroup, QComboBox, QDialog, QFileDialog,
    QGroupBox, QHBoxLayout, QInputDialog, QLabel, QListWidget,
    QMessageBox, QPushButton, QRadioButton, QSizePolicy,
    QSlider, QVBoxLayout, QWidget,
)

from utils.save_manager import (
    NAMED_BACKUPS_FOLDER,
    SAFETY_FOLDER,
    SAVE_MANAGER_CONFIG_PATH,
    TARGET_FILE,
    TARGET_PATH,
)
from utils.paths import resource_path

# ---------------------------------------------------------------------------
# Sentinel values for special sound choices
# ---------------------------------------------------------------------------

RANDOM_FART = "__random_fart__"
RANDOM_BURP = "__random_burp__"

_SPECIAL_SOUND_LABELS: dict[str, str] = {
    RANDOM_FART: "🎲  All Farts (random)",
    RANDOM_BURP: "🎲  All Burps (random)",
}
_SPECIAL_SOUND_VALUES: dict[str, str] = {v: k for k, v in _SPECIAL_SOUND_LABELS.items()}


# ---------------------------------------------------------------------------
# Sound-file helpers
# ---------------------------------------------------------------------------

def _get_fx_files(sub: str) -> list[str]:
    """Return sorted .mp3 paths from fx/<sub>/ (bundled + user locations)."""
    fx_root = resource_path("fx")
    folder = os.path.join(fx_root, sub)
    files: list[str] = []
    if os.path.isdir(folder):
        for f in sorted(os.listdir(folder)):
            if f.lower().endswith(".mp3"):
                files.append(os.path.normpath(os.path.join(folder, f)))
    return files


def _collect_all_mp3s() -> list[str]:
    """Walk fx/ recursively and return all .mp3 files (sorted)."""
    fx_root = resource_path("fx")
    seen, mp3s = set(), []
    for dirpath, _, files in os.walk(fx_root):
        for f in sorted(files):
            if f.lower().endswith(".mp3"):
                full = os.path.normpath(os.path.join(dirpath, f))
                if full not in seen:
                    seen.add(full)
                    mp3s.append(full)
    mp3s.sort()
    return mp3s


def _mp3_display_label(path: str) -> str:
    fx_root = resource_path("fx")
    try:
        rel = os.path.relpath(path, fx_root)
        if not rel.startswith(".."):
            return "fx/" + rel.replace("\\", "/")
    except ValueError:
        pass
    return os.path.basename(path)


# ---------------------------------------------------------------------------
# QMediaPlayer-based sound playback (non-blocking, fire-and-forget)
# ---------------------------------------------------------------------------

# Keep a module-level list so players are not GC'd before finishing
_active_players: list[tuple[QMediaPlayer, QAudioOutput]] = []


def _play_sound(path: str, volume: float = 1.0) -> None:
    """Play a sound file using QMediaPlayer (no pygame required)."""
    if not path or not os.path.exists(path):
        return
    player = QMediaPlayer()
    audio_out = QAudioOutput()
    player.setAudioOutput(audio_out)
    audio_out.setVolume(max(0.0, min(1.0, volume)))
    player.setSource(QUrl.fromLocalFile(os.path.abspath(path)))
    player.play()

    # Keep alive; purge finished ones to avoid memory leak
    global _active_players
    _active_players = [(p, a) for p, a in _active_players
                       if p.playbackState() != QMediaPlayer.PlaybackState.StoppedState]
    _active_players.append((player, audio_out))


# ---------------------------------------------------------------------------
# Config persistence
# ---------------------------------------------------------------------------

_DEFAULT_CONFIG: dict = {
    "mode":        "random",
    "save_backup": None,
    "quick_save":  None,
    "quick_load":  None,
    "volume":      0.8,
    "mute":        False,
}


def _load_config() -> dict:
    cfg = dict(_DEFAULT_CONFIG)
    try:
        if os.path.exists(SAVE_MANAGER_CONFIG_PATH):
            with open(SAVE_MANAGER_CONFIG_PATH, "r", encoding="utf-8") as f:
                cfg.update(json.load(f))
    except Exception as exc:
        print(f"[save_manager] Failed to load config: {exc}")
    return cfg


def _save_config(cfg: dict) -> None:
    try:
        with open(SAVE_MANAGER_CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2)
    except Exception as exc:
        print(f"[save_manager] Failed to save config: {exc}")


# ---------------------------------------------------------------------------
# Safety backup
# ---------------------------------------------------------------------------

def _create_safety_backup() -> None:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safety_path = os.path.join(SAFETY_FOLDER, f"safety_{timestamp}.sav")
    shutil.copy2(TARGET_PATH, safety_path)
    print(f"[save_manager] Safety backup created: safety_{timestamp}.sav")


# ---------------------------------------------------------------------------
# Sound Manager Dialog
# ---------------------------------------------------------------------------

_ACTIONS = [
    ("save_backup", "Save Backup"),
    ("quick_save",  "Quick Save (F7)"),
    ("quick_load",  "Quick Load (F9)"),
]


class SoundManagerDialog(QDialog):
    """Lets the user configure sounds for each save-manager action."""

    def __init__(self, parent: QWidget, sound_config: dict):
        super().__init__(parent)
        self.setWindowTitle("🔊 Sound Manager")
        self.setFixedSize(540, 440)
        self.sound_config = sound_config

        self.all_mp3s = _collect_all_mp3s()
        self.mp3_labels = (
            ["(none)"]
            + list(_SPECIAL_SOUND_LABELS.values())
            + [_mp3_display_label(p) for p in self.all_mp3s]
        )
        self._mp3_offset = 1 + len(_SPECIAL_SOUND_LABELS)

        layout = QVBoxLayout(self)
        layout.setSpacing(8)

        # --- Mode ---
        mode_group = QGroupBox("Sound Mode")
        mode_layout = QVBoxLayout(mode_group)
        self.mode_btn_group = QButtonGroup(self)
        for value, text in [
            ("random",  "🎲  Random  (fart on save · burp on load)"),
            ("classic", "🎵  Classic  (fx/save.mp3  ·  fx/load.mp3)"),
            ("custom",  "🎛  Custom  (choose per action)"),
            ("mute",    "🔇  Mute all sounds"),
        ]:
            rb = QRadioButton(text)
            rb.setProperty("mode_value", value)
            mode = sound_config.get("mode", "random")
            if (value == "mute" and sound_config.get("mute", False)) or (value == mode and value != "mute"):
                rb.setChecked(True)
            self.mode_btn_group.addButton(rb)
            mode_layout.addWidget(rb)
        self.mode_btn_group.buttonClicked.connect(self._on_mode_change)
        layout.addWidget(mode_group)

        # --- Custom assignment ---
        self.custom_group = QGroupBox("Custom Sound Assignment")
        custom_layout = QVBoxLayout(self.custom_group)
        self.combos: dict[str, QComboBox] = {}
        self.preview_btns: dict[str, QPushButton] = {}
        for action, label in _ACTIONS:
            row = QWidget()
            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(0, 0, 0, 0)

            lbl = QLabel(label)
            lbl.setFixedWidth(145)
            row_layout.addWidget(lbl)

            current_path = sound_config.get(action)
            try:
                if current_path in _SPECIAL_SOUND_LABELS:
                    idx = self.mp3_labels.index(_SPECIAL_SOUND_LABELS[current_path])
                elif current_path in self.all_mp3s:
                    idx = self.all_mp3s.index(current_path) + self._mp3_offset
                else:
                    idx = 0
            except (ValueError, TypeError):
                idx = 0

            combo = QComboBox()
            combo.addItems(self.mp3_labels)
            combo.setCurrentIndex(idx)
            combo.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            row_layout.addWidget(combo)
            self.combos[action] = combo

            btn = QPushButton("▶")
            btn.setFixedWidth(32)
            btn.clicked.connect(lambda _=False, a=action: self._preview(a))
            row_layout.addWidget(btn)
            self.preview_btns[action] = btn

            custom_layout.addWidget(row)
        layout.addWidget(self.custom_group)

        # --- Volume ---
        vol_group = QGroupBox("Volume")
        vol_layout = QHBoxLayout(vol_group)
        self.vol_slider = QSlider(Qt.Orientation.Horizontal)
        self.vol_slider.setRange(0, 100)
        self.vol_slider.setValue(int(sound_config.get("volume", 0.8) * 100))
        self.vol_slider.valueChanged.connect(lambda v: self.vol_label.setText(f"{v} %"))
        vol_layout.addWidget(self.vol_slider)
        self.vol_label = QLabel(f"{self.vol_slider.value()} %")
        self.vol_label.setFixedWidth(45)
        vol_layout.addWidget(self.vol_label)
        layout.addWidget(vol_group)

        # --- OK / Cancel ---
        btn_row = QWidget()
        btn_row_layout = QHBoxLayout(btn_row)
        btn_row_layout.setContentsMargins(0, 0, 0, 0)
        ok_btn = QPushButton("Save")
        ok_btn.setFixedWidth(100)
        ok_btn.clicked.connect(self._save)
        cancel_btn = QPushButton("Cancel")
        cancel_btn.setFixedWidth(100)
        cancel_btn.clicked.connect(self.reject)
        btn_row_layout.addStretch()
        btn_row_layout.addWidget(ok_btn)
        btn_row_layout.addWidget(cancel_btn)
        btn_row_layout.addStretch()
        layout.addWidget(btn_row)

        self._on_mode_change()

    def _get_current_mode(self) -> str:
        for btn in self.mode_btn_group.buttons():
            if btn.isChecked():
                return btn.property("mode_value")
        return "random"

    def _on_mode_change(self, _btn=None):
        is_custom = self._get_current_mode() == "custom"
        for action in self.combos:
            self.combos[action].setEnabled(is_custom)
            self.preview_btns[action].setEnabled(is_custom)

    def _preview(self, action: str):
        label = self.combos[action].currentText()
        if label == "(none)":
            return
        volume = self.vol_slider.value() / 100
        if label in _SPECIAL_SOUND_VALUES:
            sentinel = _SPECIAL_SOUND_VALUES[label]
            files = _get_fx_files("fart") if sentinel == RANDOM_FART else _get_fx_files("burp")
            if files:
                _play_sound(random.choice(files), volume=volume)
            return
        try:
            idx = self.mp3_labels.index(label) - self._mp3_offset
            _play_sound(self.all_mp3s[idx], volume=volume)
        except (ValueError, IndexError):
            pass

    def _save(self):
        mode = self._get_current_mode()
        self.sound_config["mode"] = mode if mode != "mute" else self.sound_config.get("mode", "random")
        self.sound_config["mute"] = (mode == "mute")
        self.sound_config["volume"] = self.vol_slider.value() / 100
        for action in self.combos:
            label = self.combos[action].currentText()
            if label == "(none)":
                self.sound_config[action] = None
            elif label in _SPECIAL_SOUND_VALUES:
                self.sound_config[action] = _SPECIAL_SOUND_VALUES[label]
            else:
                try:
                    idx = self.mp3_labels.index(label) - self._mp3_offset
                    self.sound_config[action] = self.all_mp3s[idx]
                except (ValueError, IndexError):
                    self.sound_config[action] = None
        self.accept()


# ---------------------------------------------------------------------------
# Save Manager Panel
# ---------------------------------------------------------------------------

class SaveManagerPanel(QWidget):
    """
    Full save-backup manager widget that can be embedded in a QStackedWidget.

    Signals
    -------
    quick_save_requested  — emitted when F7 hotkey fires (marshalled to main thread)
    quick_load_requested  — emitted when F9 hotkey fires (marshalled to main thread)
    """

    quick_save_requested = Signal()
    quick_load_requested = Signal()

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.sound_config = _load_config()
        self._hotkeys_registered = False

        # Connect signals to actual methods (main-thread safe)
        self.quick_save_requested.connect(self._quick_save)
        self.quick_load_requested.connect(lambda: self._quick_load(confirm=False))

        self._build_ui()

        # Auto-register hotkeys on startup (silently; no popup if keyboard is missing)
        self._register_hotkeys(silent=True)

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        # Title
        title = QLabel("💾 Save Manager")
        title.setStyleSheet("font-size: 16px; font-weight: bold; color: #4a9eff;")
        layout.addWidget(title)

        subtitle = QLabel(
            "Create and restore backups of your save file — "
            "even from within the game using global shortcuts."
        )
        subtitle.setWordWrap(True)
        subtitle.setStyleSheet("color: #888; font-size: 12px;")
        layout.addWidget(subtitle)

        # Top action buttons
        top_row = QWidget()
        top_layout = QHBoxLayout(top_row)
        top_layout.setContentsMargins(0, 0, 0, 0)
        top_layout.setSpacing(6)

        self._save_btn = QPushButton("💾 Save Backup")
        self._save_btn.setMinimumHeight(36)
        self._save_btn.setToolTip("Create a named backup (you choose the name)")
        self._save_btn.clicked.connect(self._create_named_backup)
        top_layout.addWidget(self._save_btn)

        self._qs_btn = QPushButton("⚡ Quick Save  F7")
        self._qs_btn.setMinimumHeight(36)
        self._qs_btn.setToolTip("Create a timestamped backup instantly (also bound to F7 globally)")
        self._qs_btn.clicked.connect(self._quick_save)
        top_layout.addWidget(self._qs_btn)

        self._ql_btn = QPushButton("📂 Quick Load  F9")
        self._ql_btn.setMinimumHeight(36)
        self._ql_btn.setToolTip("Load the most recent backup (also bound to F9 globally)")
        self._ql_btn.clicked.connect(self._quick_load)
        top_layout.addWidget(self._ql_btn)

        layout.addWidget(top_row)

        # Backup list label
        list_label = QLabel("Backups (most recent first):")
        list_label.setStyleSheet("font-size: 12px; color: #aaa;")
        layout.addWidget(list_label)

        self._list = QListWidget()
        self._list.itemDoubleClicked.connect(lambda _: self._reload_backup())
        layout.addWidget(self._list)

        # Action row
        action_row = QWidget()
        action_layout = QHBoxLayout(action_row)
        action_layout.setContentsMargins(0, 0, 0, 0)
        action_layout.setSpacing(6)

        self._reload_btn = QPushButton("🔄 Reload Selected")
        self._reload_btn.clicked.connect(self._reload_backup)
        action_layout.addWidget(self._reload_btn)

        self._rename_btn = QPushButton("✏️ Rename Selected")
        self._rename_btn.clicked.connect(self._rename_backup)
        action_layout.addWidget(self._rename_btn)

        self._export_btn = QPushButton("📤 Export Selected")
        self._export_btn.clicked.connect(self._export_backup)
        action_layout.addWidget(self._export_btn)

        self._clean_btn = QPushButton("🗑 Clean Backups (keep 5)")
        self._clean_btn.clicked.connect(self._clean_backups)
        action_layout.addWidget(self._clean_btn)

        layout.addWidget(action_row)

        # Bottom row
        bottom_row = QWidget()
        bottom_layout = QHBoxLayout(bottom_row)
        bottom_layout.setContentsMargins(0, 0, 0, 0)

        self._sound_btn = QPushButton("🔊 Sound Manager")
        self._sound_btn.clicked.connect(self._open_sound_manager)
        bottom_layout.addWidget(self._sound_btn)

        bottom_layout.addStretch()

        # Hotkey status (read-only; registration is automatic)
        self._hotkey_lbl = QLabel("⌨️ Hotkeys: not registered")
        self._hotkey_lbl.setStyleSheet("color: #888; font-size: 11px;")
        bottom_layout.addWidget(self._hotkey_lbl)


        layout.addWidget(bottom_row)

        # Safety folder info
        info_lbl = QLabel(
            f"📁 Backups: {NAMED_BACKUPS_FOLDER}\n"
            f"🛟 Safety: {SAFETY_FOLDER}"
        )
        info_lbl.setWordWrap(True)
        info_lbl.setStyleSheet("color: #666; font-size: 10px;")
        layout.addWidget(info_lbl)

        self._refresh_list()

    # ------------------------------------------------------------------
    # Keyboard hotkeys
    # ------------------------------------------------------------------

    def _toggle_hotkeys(self):
        if self._hotkeys_registered:
            self._unregister_hotkeys()
        else:
            self._register_hotkeys()

    def _register_hotkeys(self, silent: bool = False):
        try:
            import keyboard
            keyboard.add_hotkey("F7", lambda: self.quick_save_requested.emit())
            keyboard.add_hotkey("F9", lambda: self.quick_load_requested.emit())
            self._hotkeys_registered = True
            self._hotkey_lbl.setText("⌨️ Hotkeys: ✅ F7/F9 active")
            self._hotkey_lbl.setStyleSheet("color: #4caf50; font-size: 11px;")
            print("[save_manager] Global hotkeys F7/F9 registered.")
        except ImportError:
            msg = (
                "The 'keyboard' package is not installed.\n\n"
                "Install it with:  pip install keyboard\n\n"
                "Global hotkeys (F7/F9) are not available without it."
            )
            self._hotkey_lbl.setText("⌨️ Hotkeys: ⚠️ keyboard not installed")
            self._hotkey_lbl.setStyleSheet("color: #ff9800; font-size: 11px;")
            if not silent:
                QMessageBox.warning(self, "Keyboard library missing", msg)
        except Exception as exc:
            msg = (
                f"Could not register global hotkeys:\n{exc}\n\n"
                "This may require running the application as administrator."
            )
            self._hotkey_lbl.setText("⌨️ Hotkeys: ❌ registration failed")
            self._hotkey_lbl.setStyleSheet("color: #f44336; font-size: 11px;")
            if not silent:
                QMessageBox.warning(self, "Hotkey registration failed", msg)

    def _unregister_hotkeys(self):
        try:
            import keyboard
            keyboard.remove_hotkey("F7")
            keyboard.remove_hotkey("F9")
        except Exception:
            pass
        self._hotkeys_registered = False
        self._hotkey_lbl.setText("⌨️ Hotkeys: not registered")
        self._hotkey_lbl.setStyleSheet("color: #888; font-size: 11px;")
        print("[save_manager] Global hotkeys unregistered.")

    def closeEvent(self, event):
        if self._hotkeys_registered:
            self._unregister_hotkeys()
        super().closeEvent(event)

    # ------------------------------------------------------------------
    # Sound
    # ------------------------------------------------------------------

    def _open_sound_manager(self):
        dlg = SoundManagerDialog(self, self.sound_config)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            _save_config(self.sound_config)

    def _play_for_action(self, action: str):
        if self.sound_config.get("mute", False):
            return
        mode = self.sound_config.get("mode", "random")
        volume = self.sound_config.get("volume", 0.8)

        if mode == "random":
            if action in ("save_backup", "quick_save"):
                files = _get_fx_files("fart")
                if files:
                    _play_sound(random.choice(files), volume=volume)
            elif action == "quick_load":
                files = _get_fx_files("burp")
                if files:
                    _play_sound(random.choice(files), volume=volume)

        elif mode == "classic":
            if action in ("save_backup", "quick_save"):
                _play_sound(resource_path(os.path.join("fx", "save.mp3")), volume=volume)
            elif action == "quick_load":
                _play_sound(resource_path(os.path.join("fx", "load.mp3")), volume=volume)

        elif mode == "custom":
            path = self.sound_config.get(action)
            if path == RANDOM_FART:
                files = _get_fx_files("fart")
                if files:
                    _play_sound(random.choice(files), volume=volume)
            elif path == RANDOM_BURP:
                files = _get_fx_files("burp")
                if files:
                    _play_sound(random.choice(files), volume=volume)
            elif path and os.path.exists(path):
                _play_sound(path, volume=volume)

    # ------------------------------------------------------------------
    # List refresh
    # ------------------------------------------------------------------

    def _refresh_list(self):
        self._list.clear()
        try:
            folders = [
                f for f in os.listdir(NAMED_BACKUPS_FOLDER)
                if os.path.isdir(os.path.join(NAMED_BACKUPS_FOLDER, f))
            ]
        except FileNotFoundError:
            return
        folders.sort(
            key=lambda f: os.path.getctime(os.path.join(NAMED_BACKUPS_FOLDER, f)),
            reverse=True,
        )
        for f in folders:
            path = os.path.join(NAMED_BACKUPS_FOLDER, f)
            ctime = os.path.getctime(path)
            date_str = datetime.fromtimestamp(ctime).strftime("%d/%m/%y %H:%M:%S")
            self._list.addItem(f"{date_str}   {f}")

    def _selected_backup_name(self) -> str | None:
        item = self._list.currentItem()
        if not item:
            return None
        return item.text().split("   ", 1)[1]

    # ------------------------------------------------------------------
    # Backup operations
    # ------------------------------------------------------------------

    def _quick_save(self):
        name = f"quicksave_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        folder_path = os.path.join(NAMED_BACKUPS_FOLDER, name)
        try:
            os.makedirs(folder_path, exist_ok=True)
            shutil.copy2(TARGET_PATH, os.path.join(folder_path, TARGET_FILE))
            self._play_for_action("quick_save")
            print(f"[save_manager] ⚡ Quick save created: {name}")
        except Exception as exc:
            QMessageBox.critical(self, "Quick Save Error", str(exc))
            print(f"[save_manager] ❌ Quick save failed: {exc}")
        self._refresh_list()

    def _quick_load(self, confirm: bool = True):
        if self._list.count() == 0:
            QMessageBox.information(self, "Quick Load", "No backup available.")
            return

        name = self._list.item(0).text().split("   ", 1)[1]
        folder = os.path.join(NAMED_BACKUPS_FOLDER, name)
        backup_file = os.path.join(folder, TARGET_FILE)

        if not os.path.exists(backup_file):
            QMessageBox.critical(self, "Error", "Backup file is missing.")
            return

        if confirm:
            answer = QMessageBox.question(
                self, "Quick Load",
                f"Load most recent backup <b>{name}</b>?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if answer != QMessageBox.StandardButton.Yes:
                return

        _create_safety_backup()
        try:
            shutil.copy2(backup_file, TARGET_PATH)
            self._play_for_action("quick_load")
            print(f"[save_manager] ⚡ Quick loaded: {name}")
        except Exception as exc:
            QMessageBox.critical(self, "Quick Load Error", str(exc))
            print(f"[save_manager] ❌ Quick load failed: {exc}")

    def _create_named_backup(self):
        name, ok = QInputDialog.getText(self, "Save Backup", "Backup name:")
        if not ok or not name.strip():
            return

        safe_name = name.strip().replace(" ", "_")
        folder_path = os.path.join(NAMED_BACKUPS_FOLDER, safe_name)

        if os.path.exists(folder_path):
            answer = QMessageBox.question(
                self, "Overwrite?",
                f"A backup named <b>{safe_name}</b> already exists. Overwrite?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if answer != QMessageBox.StandardButton.Yes:
                return
            shutil.rmtree(folder_path)

        os.makedirs(folder_path)
        shutil.copy2(TARGET_PATH, os.path.join(folder_path, TARGET_FILE))
        self._play_for_action("save_backup")
        print(f"[save_manager] ⭐ Named backup created: {safe_name}")
        self._refresh_list()

    def _reload_backup(self):
        name = self._selected_backup_name()
        if not name:
            QMessageBox.information(self, "Reload", "Select a backup first.")
            return

        backup_file = os.path.join(NAMED_BACKUPS_FOLDER, name, TARGET_FILE)
        if not os.path.exists(backup_file):
            QMessageBox.critical(self, "Error", "Backup file is missing.")
            return

        answer = QMessageBox.question(
            self, "Reload Backup",
            f"Restore backup <b>{name}</b>?\n\n"
            "A safety copy will be created automatically.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return

        _create_safety_backup()
        try:
            shutil.copy2(backup_file, TARGET_PATH)
            print(f"[save_manager] 🔄 Reloaded backup: {name}")
        except Exception as exc:
            QMessageBox.critical(self, "Reload Error", str(exc))

    def _rename_backup(self):
        name = self._selected_backup_name()
        if not name:
            QMessageBox.information(self, "Rename", "Select a backup first.")
            return

        old_path = os.path.join(NAMED_BACKUPS_FOLDER, name)
        new_name, ok = QInputDialog.getText(
            self, "Rename Backup", "New name:", text=name
        )
        if not ok or not new_name.strip():
            return

        safe_name = new_name.strip().replace(" ", "_")
        if safe_name == name:
            return

        new_path = os.path.join(NAMED_BACKUPS_FOLDER, safe_name)
        if os.path.exists(new_path):
            QMessageBox.warning(
                self, "Rename", f"A backup named '{safe_name}' already exists."
            )
            return

        try:
            os.rename(old_path, new_path)
            print(f"[save_manager] ✏️ Renamed '{name}' → '{safe_name}'")
        except Exception as exc:
            QMessageBox.critical(self, "Rename Error", str(exc))
            return

        self._refresh_list()

    def _export_backup(self):
        name = self._selected_backup_name()
        if not name:
            QMessageBox.information(self, "Export", "Select a backup first.")
            return

        backup_file = os.path.join(NAMED_BACKUPS_FOLDER, name, TARGET_FILE)
        if not os.path.exists(backup_file):
            QMessageBox.critical(self, "Error", "Backup file is missing.")
            return

        dest, _ = QFileDialog.getSaveFileName(
            self, "Export Backup",
            os.path.join(os.path.expanduser("~"), TARGET_FILE),
            "Save files (*.sav);;All files (*.*)",
        )
        if not dest:
            return

        try:
            shutil.copy2(backup_file, dest)
            QMessageBox.information(self, "Export", f"Backup exported to:\n{dest}")
            print(f"[save_manager] 📤 Exported '{name}' → {dest}")
        except Exception as exc:
            QMessageBox.critical(self, "Export Error", str(exc))

    def _clean_backups(self):
        try:
            folders = [
                f for f in os.listdir(NAMED_BACKUPS_FOLDER)
                if os.path.isdir(os.path.join(NAMED_BACKUPS_FOLDER, f))
            ]
        except FileNotFoundError:
            folders = []

        folders.sort(
            key=lambda f: os.path.getctime(os.path.join(NAMED_BACKUPS_FOLDER, f)),
            reverse=True,
        )
        to_delete = folders[5:]

        try:
            safety_files = [
                f for f in os.listdir(SAFETY_FOLDER)
                if os.path.isfile(os.path.join(SAFETY_FOLDER, f))
            ]
        except FileNotFoundError:
            safety_files = []

        safety_files.sort(
            key=lambda f: os.path.getctime(os.path.join(SAFETY_FOLDER, f)),
            reverse=True,
        )
        safety_to_delete = safety_files[5:]

        if not to_delete and not safety_to_delete:
            QMessageBox.information(
                self, "Clean Backups", "Nothing to delete (5 or fewer backups)."
            )
            return

        answer = QMessageBox.question(
            self, "Clean Backups",
            f"Delete <b>{len(to_delete)}</b> backup(s) and "
            f"<b>{len(safety_to_delete)}</b> safety backup(s), "
            "keeping the 5 most recent of each?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return

        for f in to_delete:
            shutil.rmtree(os.path.join(NAMED_BACKUPS_FOLDER, f))
            print(f"[save_manager] 🗑 Deleted backup: {f}")

        for f in safety_to_delete:
            os.remove(os.path.join(SAFETY_FOLDER, f))
            print(f"[save_manager] 🗑 Deleted safety backup: {f}")

        self._refresh_list()

