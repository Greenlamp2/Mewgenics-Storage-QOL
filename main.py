import sys

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from ui.main_window import MainWindow
from utils.paths import resource_path
from utils.save_manager import TARGET_PATH
from utils.versions import is_app_up_most_to_date

if __name__ == "__main__":
    path = TARGET_PATH

    if not is_app_up_most_to_date(path):
        raise Exception("App is NOT up to date!")

    app = QApplication(sys.argv)
    app.setWindowIcon(QIcon(resource_path("assets/icons/tokens/very_rare.png")))
    window = MainWindow(path)
    window.show()
    sys.exit(app.exec())
