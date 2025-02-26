import sys
from PyQt6.QtWidgets import QApplication, QMainWindow, QLabel, QPushButton, QVBoxLayout, QWidget
from laser_timing import Ui_MainWindow
from vironAPI import initialize, send_receive

""" CONSTANTS """
LASERS = {"v1" : {"HOST":"192.168.103.105", "PORT":"25", "MAC":"0080A36BE41D"}}

class LaserGUI(QMainWindow, Ui_MainWindow):
    def __init__(self):
        super().__init__()
        self.ui = Ui_MainWindow()
        self.ui.setupUi(self)

        lasers = ["v1", "v2", "c1", "c2", "c3", "c4", "c5"]
        # lasers = [v for v in self.ui.__dict__.values() if '_enabled' in v.objectName()]
        for l in lasers:
            ll = self.ui.__dict__[l + "_enabled"]
            ll.clicked.connect(self.enable)
            ll = self.ui.__dict__[l + "_init"]
            ll.clicked.connect(self.initialize)

    def enable(self):
        button = self.sender()
        if button.text() == "Enabled":
            button.setText("Disabled")
        else:  
            button.setText("Enabled")

    async def initialize(self):
        button = self.sender()
        if button.objectName().startswith("v"):
            await initialize(host=LASERS["v1"]["HOST"], port=LASERS["v1"]["PORT"], mac=LASERS["v1"]["MAC"])


if __name__ == '__main__':
    app = QApplication(sys.argv)
    window = LaserGUI()
    window.show()
    sys.exit(app.exec())