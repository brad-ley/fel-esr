import sys, asyncio 
import time
from PyQt6.QtWidgets import QApplication, QMainWindow, QLabel, QPushButton, QVBoxLayout, QWidget, QTextEdit
from PyQt6.QtCore import QThread, pyqtSignal, QTimer
from laser_timing import Ui_MainWindow
from vironAPI import send_receive, login_command, create_reader_writer 

MINCURR = 120

class LaserGUI(QMainWindow, Ui_MainWindow):
    def __init__(self):
        super().__init__()
        self.ui = Ui_MainWindow()
        self.ui.setupUi(self)

        self.lasers = {"v1":{}, "v2":{}, "c1":{}, "c2":{}, "c3":{}, "c4":{}, "c5":{}}
        # lasers = [v for v in self.ui.__dict__.values() if '_enabled' in v.objectName()]
        for l in self.lasers:
            ll = self.ui.__dict__[l + "_enabled"]
            ll.clicked.connect(self.enable_laser)
            ll = self.ui.__dict__[l + "_init"]
            ll.clicked.connect(self.initialize)
            ll = self.ui.__dict__[l + "_power"]
            ll.sliderReleased.connect(self.set_power_laser)
            ll = self.ui.__dict__[l + "_trig_diode"]
            ll.clicked.connect(self.set_trigger_laser)
            ll = self.ui.__dict__[l + "_trig_qs"]
            ll.clicked.connect(self.set_trigger_laser)
            # TODO: handle timing if in EI, EE, etc mode -- set defaults and disable timing input if it is already fixed by the mode
            # TODO: add diagnostic window to top of GUI to show laser status, etc
        
        self.make_laser_dict()

        if sys.platform == "win32":
            asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

        # Ensure an event loop is created if one does not exist
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)

        self.flash_timer = QTimer(self)
        self.flash_timer.timeout.connect(self.toggle_button_color)

    def get_laser_name(self, sender):
        return sender.objectName().split("_")[0] # relies on naming convention <laser><number>_<action>

    def make_laser_dict(self):
        lasers = [ii.objectName().rstrip("_enabled") for ii  in self.findChildren(QPushButton) if "_enabled" in ii.objectName()]
        widgets = self.findChildren(QTextEdit)
        for laser in lasers:
            if laser.startswith("v"):
                ip = next(ii.toPlainText() for ii in widgets if ii.objectName() == laser + "_ip")
                host, port = ip.split(":")
                mac = next(ii.toPlainText() for ii in widgets if ii.objectName() == laser + "_mac")
                self.lasers[laser]["HOST"] = host
                self.lasers[laser]["PORT"] = port
                self.lasers[laser]["MAC"] = mac

    def enable_laser(self):
        l = self.get_laser_name(self.sender())
        if l.startswith("v"):
            if self.sender().text() == "Enable":
                self.loop.run_until_complete(self.send_receive_laser(l, "$FIRE\n"))
                self.sender().setText("Disable")
            else:  
                self.sender().setText("Enable")
                self.loop.run_until_complete(self.send_receive_laser(l, "$STANDBY\n"))

    def initialize(self):
        l = self.get_laser_name(self.sender())
        if l.startswith("v"):
            if self.sender().isChecked():
                self.loop.run_until_complete(self.init_laser(l))
                self.sender().setText("Standby")
            else:
                self.loop.run_until_complete(self.send_receive_laser(l, "$STOP\n"))
                self.sender().setText("Initialize")

    def set_power_laser(self):
        l = self.get_laser_name(self.sender())
        if l.startswith("v"):
            self.loop.run_until_complete(self.send_receive_laser(l, f"$DCURR {MINCURR + (self.lasers[l]["maxcurr"] - MINCURR) / 100 * self.sender().value()}\n"))
    
    def set_trigger_laser(self):
        l = self.get_laser_name(self.sender())
        trigger_buttons = [ii for ii in self.findChildren(QPushButton) if f"{l}_trig_" in ii.objectName()]
        if l.startswith("v"):
            # checked means interal, unchecked (default) means external
            def bool_to_code(b):
                return "I" if b else "E"
            def code_to_bool(c):
                return c == "I"

            other = next(ii for ii in trigger_buttons if self.sender().objectName() not in ii.objectName())
            trig = bool_to_code(self.sender().isChecked()) + bool_to_code(other.isChecked())
            if self.sender().objectName().endswith("qs"):
                # want to swap order if was triggered by qs button because the laser wants the order to go diode-qs. 
                trig = trig[::-1]
            
            if trig == "IE":
                # IE is forbidden, can't trigger internal then external -- that would be non-causal
                trig = bool_to_code(self.sender().isChecked()) + bool_to_code(self.sender().isChecked())
                other.setChecked(self.sender().isChecked())
                for button in [self.sender(), other]:
                    button.setText("Internal" if self.sender().isChecked() else "External")

            self.loop.run_until_complete(self.send_receive_laser(l, f"$TRIG {trig}\n"))

            self.sender().setText("Internal" if self.sender().isChecked() else "External")

    async def init_laser(self, laser):
        if not ("reader" in self.lasers[laser] or "writer" in self.lasers[laser]):
            reader, writer = await create_reader_writer(
                host=self.lasers[laser]["HOST"], 
                port=self.lasers[laser]["PORT"], 
                mac=self.lasers[laser]["MAC"]
                )
            await send_receive(reader, writer, login_command(self.lasers[laser]["MAC"]))
            maxcurr = await send_receive(reader, writer, "$MAXCURR ?\n")
            self.lasers[laser]["reader"], self.lasers[laser]["writer"], self.lasers[laser]["maxcurr"] = reader, writer, float(maxcurr.split(" ")[1])
        await send_receive(self.lasers[laser]["reader"], self.lasers[laser]["writer"], "$STANDBY\n")

    async def send_receive_laser(self, laser, command):
        try:
            await send_receive(self.lasers[laser]["reader"], self.lasers[laser]["writer"], command)
        except KeyError:
            self.initialize_button = self.findChildren(QPushButton, f"{laser}_init")[0]
            self.flash_count = 0
            self.flash_timer.start(100)
            print("Laser not initialized")

    def toggle_button_color(self):
        self.initialize_button.setStyleSheet("background-color: red" if self.flash_count % 2 else "")

        self.flash_count += 1

        if self.flash_count >= 10:
            self.flash_timer.stop()
            self.initialize_button.setStyleSheet("")


def main():
    app = QApplication(sys.argv)
    window = LaserGUI()
    window.show()

    sys.exit(app.exec())


if __name__ == '__main__':
    main()