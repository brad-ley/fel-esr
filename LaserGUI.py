import sys, asyncio 
from PyQt6.QtWidgets import QApplication, QMainWindow, QLabel, QPushButton, QVBoxLayout, QWidget, QTextEdit
from PyQt6.QtCore import QThread, pyqtSignal
from laser_timing import Ui_MainWindow
from vironAPI import send_receive, login_command, create_reader_writer 

class LaserGUI(QMainWindow, Ui_MainWindow):
    def __init__(self):
        super().__init__()
        self.ui = Ui_MainWindow()
        self.ui.setupUi(self)

        self.lasers = {"v1":{}, "v2":{}, "c1":{}, "c2":{}, "c3":{}, "c4":{}, "c5":{}}
        # lasers = [v for v in self.ui.__dict__.values() if '_enabled' in v.objectName()]
        for l in self.lasers:
            ll = self.ui.__dict__[l + "_enabled"]
            ll.clicked.connect(self.enable)
            ll = self.ui.__dict__[l + "_init"]
            ll.clicked.connect(self.initialize)
        
        self.make_laser_dict()

        if sys.platform == "win32":
            asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

        self.loop = asyncio.get_event_loop()

    def make_laser_dict(self):
        lasers = [ii.objectName().rstrip("_enabled") for ii  in self.findChildren(QPushButton) if "_enabled" in ii.objectName()]
        widgets = self.findChildren(QTextEdit)
        for laser in lasers:
            if laser.startswith("v"):
                ip = next(ii.toPlainText() for ii in widgets if ii.objectName() == laser + "_ip")
                print(ip)
                host, port = ip.split(":")
                mac = next(ii.toPlainText() for ii in widgets if ii.objectName() == laser + "_mac")
                self.lasers[laser]["HOST"] = host
                self.lasers[laser]["PORT"] = port
                self.lasers[laser]["MAC"] = mac

    def enable(self):
        button = self.sender()
        if button.text() == "Enabled":
            button.setText("Disabled")
        else:  
            button.setText("Enabled")

    def initialize(self):
        l = self.sender().objectName().strip("_init")
        if self.sender().isChecked():
            self.loop.run_until_complete(self.init_laser(l))
            self.sender().setText("Standby")
        else:
            self.loop.run_until_complete(self.stop_laser(l))
            self.sender().setText("Initialize")

    async def init_laser(self, laser):
        if laser.startswith("v"):
            if not ("reader" in self.lasers[laser] or "writer" in self.lasers[laser]):
                reader, writer = await create_reader_writer(
                    host=self.lasers[laser]["HOST"], 
                    port=self.lasers[laser]["PORT"], 
                    mac=self.lasers[laser]["MAC"]
                    )
                await send_receive(reader, writer, login_command(self.lasers[laser]["MAC"]))
                self.lasers[laser]["reader"], self.lasers[laser]["writer"] = reader, writer
            await send_receive(self.lasers[laser]["reader"], self.lasers[laser]["writer"], "$STANDBY\n")

    async def stop_laser(self, laser):
        if laser.startswith("v"):
            await send_receive(self.lasers[laser]["reader"], self.lasers[laser]["writer"], "$STOP\n")


def main():
    app = QApplication(sys.argv)
    window = LaserGUI()
    window.show()

    sys.exit(app.exec())


if __name__ == '__main__':
    main()