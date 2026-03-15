import sys

from PySide6.QtWidgets import QApplication

from ui.main_window import MainWindow
from utils.versions import is_app_up_most_to_date


if __name__ == "__main__":
    path = "steamcampaign01.sav"

    if not is_app_up_most_to_date(path):
        raise Exception("App is NOT up to date!")

    app = QApplication(sys.argv)
    window = MainWindow(path)
    window.show()
    sys.exit(app.exec())
