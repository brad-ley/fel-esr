import sys, asyncio
from PyQt6.QtWidgets import QApplication, QMainWindow, QLabel, QPushButton, QVBoxLayout, QWidget
from PyQt6.QtCore import QThread, pyqtSignal
from laser_timing import Ui_MainWindow
from vironAPI import initialize, send_receive

""" CONSTANTS """
LASERS = {"v1" : {"HOST":"192.168.103.105", "PORT":"25", "MAC":"0080A36BE41D"}}

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

    def enable(self):
        button = self.sender()
        if button.text() == "Enabled":
            button.setText("Disabled")
        else:  
            button.setText("Enabled")

    def initialize(self):
        l = self.sender().objectName().strip("_init")
        if self.sender().isChecked():
            self.worker_thread = WorkerThread(self.sender())
            self.worker_thread.result_signal.connect(self.on_task_complete)
            reader, writer = self.worker_thread.init_laser()
            if reader or writer:
                self.lasers[l]["reader"], self.lasers[l]["writer"] = reader, writer
        else:
            self.worker_thread = WorkerThread(self.sender())
            self.worker_thread.result_signal.connect(self.on_task_complete)
            self.worker_thread.stop_laser(self.lasers[l]["reader"], self.lasers[l]["writer"])

    def cleanup_thread(self):
        self.worker_thread.quit()
        self.worker_thread.wait()

    def on_task_complete(self, result):
        print(f"Task complete: {result}")
        self.cleanup_thread()


class WorkerThread(QThread):
    result_signal = pyqtSignal(str)

    def __init__(self, laserObject):
        self.laserObj = laserObject
        self.laser = self.laserObj.objectName().strip("_init")
        super().__init__()

    def init_laser(self):
        reader, writer = asyncio.run(self.initialize())
        return reader, writer

    def stop_laser(self, reader, writer):
        asyncio.run(self.stop(reader, writer))

    async def initialize(self):
        if self.laser.startswith("v"):
            reader, writer = await initialize(host=LASERS[self.laser]["HOST"], port=LASERS[self.laser]["PORT"], mac=LASERS[self.laser]["MAC"])
            if reader or writer:
                self.result_signal.emit("Initialization complete")
                self.laserObj.setText("Ready to fire")
            else:
                self.result_signal.emit("Initialization failed")
                self.laserObj.setText("Initialize")
                self.laserObj.setChecked(False)
            
        return reader, writer


    ### This function is not yet working -- just crashes in send_receive
    async def stop(self, reader, writer):
        print(reader, writer)
        if self.laser.startswith("v"):
            await send_receive(reader, writer, "$STOP\n")
            self.laserObj.setText("Initialize")
            self.laserObj.setChecked(False)

if __name__ == '__main__':
    app = QApplication(sys.argv)
    window = LaserGUI()
    window.show()
    sys.exit(app.exec())