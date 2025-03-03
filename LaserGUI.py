import asyncio
import inspect
from pydoc import ispath
import sys
import functools

from pathlib import Path

from numpy import save
from constants import FLASHES, MINCURR
from laser_timing import Ui_MainWindow
from PyQt6.QtCore import QTimer, QSettings
from PyQt6.QtWidgets import (
    QApplication,
    QMainWindow,
    QPushButton,
    QTextEdit,
    QTextBrowser,
    QDoubleSpinBox,
    QComboBox,
    QFileDialog,
    QSlider,
    QMessageBox
)
from PyQt6.QtGui import QTextCursor
from vironAPI import create_reader_writer, login_command, send_receive

def bool_to_code(b: bool) -> str:  # noqa: FBT001 ignore the positional boolean
    return "I" if b else "E"

def code_to_bool(c: str) -> bool:
    return c == "I"


class LaserGUI(QMainWindow, Ui_MainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.ui = Ui_MainWindow()
        self.ui.setupUi(self)

        self.lasers = {"v1": {}, "v2": {}, "c1": {}, "c2": {}, "c3": {}, "c4": {}, "c5": {}}
        # lasers = [v for v in self.ui.__dict__.values() if '_enabled' in v.objectName()]
        for l in self.lasers:  # noqa: E741
            ll = self.ui.__dict__[l + "_enabled"]
            ll.clicked.connect(self.enable_laser)
            ll = self.ui.__dict__[l + "_init"]
            ll.clicked.connect(self.initialize)
            ll = self.ui.__dict__[l + "_power"]
            ll.sliderReleased.connect(self.set_power_laser)
            ld = self.ui.__dict__[l + "_trig_diode"]
            ld.clicked.connect(self.set_trigger_laser)
            ld.clicked.connect(self.set_timings)

            lq = self.ui.__dict__[l + "_trig_qs"]
            lq.clicked.connect(self.set_trigger_laser)
            lq.clicked.connect(self.set_timings)
            self.lasers[l]["trig"] = bool_to_code(ld.isChecked()) + bool_to_code(lq.isChecked())
            
            ll = self.ui.__dict__[l + "_timing_diode"]
            ll.valueChanged.connect(self.set_timings)
            if not ld.isChecked():
                ll.setEnabled(False)
            ll = self.ui.__dict__[l + "_timing_qs"]
            ll.valueChanged.connect(self.set_timings)
            """
            input if it is already fixed by the mode
            - TODO(Brad): try with multiple lasers connected
            """
        
        ll = self.ui.__dict__["save_settings"]
        ll.clicked.connect(self.save_settings)
        QApplication.instance().aboutToQuit.connect(self.save_settings)
        # want to run the save settings to device .ini when app is closed so that if it is reopened it will have the same settings
    
        ll = self.ui.__dict__["load_settings"]
        ll.clicked.connect(self.load_settings)
        ll = self.ui.__dict__["unlock_connections"]
        ll.clicked.connect(self.unlock_connections)

        ll = self.ui.__dict__["file_browser"]
        ll.clicked.connect(self.open_file_dialog)

        self.file_path_input = self.ui.__dict__["savepath"]

        self.make_laser_dict()

        if sys.platform == "win32":
            asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

        # Ensure an event loop is created if one does not exist
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)

        self.flash_timer = QTimer(self)
        self.flash_timer.timeout.connect(self.toggle_button_color)

        self.status_text = ""
        self.status_bar = self.findChildren(QTextBrowser, "status")[0]

        self.settings_config = QSettings("SherwinLab", "LaserControlApp")
        self.load_settings()

    def open_file_dialog(self) -> None:
        # options = QFileDialog.Option.DontUseNativeDialog
        file_path, _ = QFileDialog.getOpenFileName(self, "Select File", "", "*.ini")
        if file_path:
            self.file_path_input.setText(file_path)
        
    def unlock_connections(self) -> None:
        connections = [ii for ii in self.findChildren(QTextEdit) if ii.objectName().endswith(("_ip", "_mac"))]
        connections += [ii for ii in self.findChildren(QComboBox) if ii.objectName().endswith("_com")]
        for conn in connections:
            conn.setEnabled(not conn.isEnabled())
            self.sender().setText("Lock connection settings" if conn.isEnabled() else "Unlock connection settings")
            self.sender().setStyleSheet("QPushButton {\n"
"    background-color:rgb(170, 255, 127);  /* orange background */\n"
"    padding: 0px 0px;         /* Padding */\n"
"    border-radius: 3px;        /* Rounded corners */\n"
"    border: .5px solid gray;\n"
"    color: black;\n"
"}\n"
"\n"
"QPushButton:hover {\n"
"    background-color:rgb(150, 255, 107);  /* Darker green on hover */\n"
"}\n"
"\n"
"QPushButton:pressed {\n"
"    background-color:rgb(130, 255, 87);  /* Even darker green when pressed */\n"
"}\n"
"" if conn.isEnabled() else "QPushButton {\n"
"    background-color: rgb(255, 170, 0);  /* orange background */\n"
"    padding: 0px 0px;         /* Padding */\n"
"    border-radius: 3px;        /* Rounded corners */\n"
"    border: .5px solid gray;\n"
"    color: black;\n"
"}\n"
"\n"
"QPushButton:hover {\n"
"    background-color:rgb(255, 150, 0);  /* Darker green on hover */\n"
"}\n"
"\n"
"QPushButton:pressed {\n"
"    background-color: rgb(255, 130, 0);  /* Even darker green when pressed */\n"
"}\n"
"")


    def not_initialized_handler(func) -> object:
        @functools.wraps(func)
        async def wrapper(self, *args, **kwargs):
            l = self.get_laser_name(self.sender())
            try:
                if inspect.iscoroutinefunction(func):
                    resp = await func(self, *args, **kwargs)
                else:
                    resp = func(self, *args, **kwargs)
            except KeyError:
                self.initialize_button = self.findChildren(QPushButton, f"{l}_init")[0]
                self.flash_count = 0
                self.flash_timer.start(100)
                resp = f"{l}: Laser not initialized\n"
            finally:
                self.status_update(resp)

        return wrapper

    def get_laser_name(self, sender: object) -> str:
        return sender.objectName().split("_")[
            0
        ]  # relies on naming convention <laser><number>_<action>

    def make_laser_dict(self) -> None:
        lasers = [
            self.get_laser_name(ii)
            for ii in self.findChildren(QPushButton)
            if "_enabled" in ii.objectName()
        ]
        widgets = self.findChildren(QTextEdit)
        for laser in lasers:
            if laser.startswith("v"):
                ip = next(ii.toPlainText() for ii in widgets if ii.objectName() == laser + "_ip")
                host, port = ip.split(":")
                mac = next(ii.toPlainText() for ii in widgets if ii.objectName() == laser + "_mac")
                self.lasers[laser]["HOST"] = host
                self.lasers[laser]["PORT"] = port
                self.lasers[laser]["MAC"] = mac

    def enable_laser(self) -> None:
        l = self.get_laser_name(self.sender())  # noqa: E741
        if l.startswith("v"):
            if self.sender().text() == "Fire":
                self.loop.run_until_complete(self.send_receive_laser(l, "$FIRE\n"))
                self.sender().setText("Disable")
            else:
                self.sender().setText("Fire")
                self.loop.run_until_complete(self.send_receive_laser(l, "$STANDBY\n"))

    def initialize(self) -> None:
        l = self.get_laser_name(self.sender())  # noqa: E741
        if l.startswith("v"):
            if self.sender().isChecked():
                self.loop.run_until_complete(self.init_laser(l))
                self.set_power_laser(l)
                self.init_trigger_laser(l)
            else:
                self.loop.run_until_complete(self.send_receive_laser(l, "$STOP\n"))

    def init_trigger_laser(self, l) -> None:
        self.loop.run_until_complete(self.send_receive_laser(
            l, 
            f"$TRIG {self.lasers[l]["trig"]}\n"
        ))


    def set_power_laser(self, l=None) -> None:
        if l is None:
            l = self.get_laser_name(self.sender())  # noqa: E741
        self.loop.run_until_complete(self.send_receive_laser(
            l,
            f"$DCURR {
                MINCURR
                + (self.lasers[l]['maxcurr'] - MINCURR) / 100 * self.ui.__dict__[l+"_power"].value()
            }\n",
        ))

    def set_trigger_laser(self, *args, **kwargs) -> None:
        l = self.get_laser_name(self.sender())  # noqa: E741
        trigger_buttons = [
            ii for ii in self.findChildren(QPushButton) if f"{l}_trig_" in ii.objectName()
        ]
        if l.startswith("v"):
            # checked means interal, unchecked (default) means external
            other = next(
                ii for ii in trigger_buttons if self.sender().objectName() not in ii.objectName()
            )
            trig = bool_to_code(self.sender().isChecked()) + bool_to_code(other.isChecked())
            if self.sender().objectName().endswith("qs"):
                # want to swap order if was triggered by qs button
                trig = trig[::-1]
            if trig == "IE":
                # IE is forbidden, can't trigger internal then external -- that would be non-causal
                trig = bool_to_code(self.sender().isChecked()) + bool_to_code(
                    self.sender().isChecked(),
                )
                other.setChecked(self.sender().isChecked())
                for button in [self.sender(), other]:
                    button.setText("Internal" if self.sender().isChecked() else "External")
            self.loop.run_until_complete(self.send_receive_laser(l, f"$TRIG {trig}\n"))
            self.lasers[l]["trig"] = trig
            self.sender().setText("Internal" if self.sender().isChecked() else "External")

    def set_timings(self, *args, **kwargs) -> None:
        l = self.get_laser_name(self.sender())  # noqa: E741
        self.loop.run_until_complete(self.set_timings_laser(l))

    def save_settings(self):
        self.loop.run_until_complete(self.save_settings_laser())
    
    async def save_settings_laser(self):
        def save_widgets(settings):
            for child in buttons:
                if not any([child.objectName().endswith(ii) for ii in skipped_names]):
                    settings.setValue(f"{child.objectName()}", child.isChecked())

            for child in timings:
                if not any([child.objectName().endswith(ii) for ii in skipped_names]):
                    settings.setValue(f"{child.objectName()}", child.value())
                    settings.setValue(f"{child.objectName()}_enabled", child.isEnabled())

            for child in inputs:
                if not any([child.objectName().endswith(ii) for ii in skipped_names]):
                    settings.setValue(f"{child.objectName()}", child.toPlainText())
                    settings.setValue(f"{child.objectName()}_enabled", child.isEnabled())

            for child in dropdowns:
                if not any([child.objectName().endswith(ii) for ii in skipped_names]):
                    settings.setValue(f"{child.objectName()}", child.currentText())

            for child in sliders:
                if not any([child.objectName().endswith(ii) for ii in skipped_names]):
                    settings.setValue(f"{child.objectName()}", child.value())

        buttons = self.findChildren(QPushButton)
        timings = self.findChildren(QDoubleSpinBox)
        inputs = self.findChildren(QTextEdit)
        dropdowns = self.findChildren(QComboBox)
        sliders = self.findChildren(QSlider)
        # children = set(buttons + timings + inputs + dropdowns)
        skipped_names = set(["status", "_enabled", "_settings", "unlock_connections", "_init", "send_times"]) # all the stuff that doesn't need to be saved

        if not isinstance(self.sender(), QApplication):
            path = Path(self.file_path_input.toPlainText())
            if Path(path).parent.exists() and Path(path).suffix == ".ini":
                save = False
                if Path(path).exists():
                    response = QMessageBox.warning(self, "File Overwrite Warning", f"The file {path} already exists. Do you want to overwrite it?", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No)

                    if response == QMessageBox.StandardButton.Yes:
                        save = True
                    else:
                        resp = "File save cancelled.\n"
                else:
                    save = True
                
                if save:
                    settings = QSettings(str(path), QSettings.Format.IniFormat)

                    save_widgets(settings)
                    settings.sync()

                    resp  = f"Saved succesfully to {path.name}.\n" 
            else:
                resp = f"'.ini' path error.\n" 

            self.status_update(resp)

        save_widgets(self.settings_config)
        self.settings_config.sync()

    def load_settings(self):
        # self.loop.run_until_complete(self.load_settings_laser)
        self.load_settings_laser()

    def load_settings_laser(self):
        settings = None
        if self.sender() is not None:
            path = Path(self.file_path_input.toPlainText())
            if Path(path).parent.exists() and Path(path).suffix == ".ini":
                settings = QSettings(str(path), QSettings.Format.IniFormat)
                loadfrom = path.name
                resp = f"Loaded from {loadfrom}.\n"
            else:
                resp = f"'.ini' path error.\n" 
        else:
            settings = self.settings_config # handle for initial opening of the gui
            loadfrom = "previous"
            resp = f"Loaded from {loadfrom}.\n"

        if settings is not None:
            for setting in settings.allKeys():
                if not setting.endswith("_enabled"): # skip the buttons 'enabled' settings since they do not correspond to a real widget
                    widget = self.ui.__dict__[setting]
                    widget.blockSignals(True)
                    if "_timing" in setting and not setting.endswith("_enabled"):
                        # this is the timing valuebox
                        # will also have sister value for enable
                        widget.setValue(float(settings.value(setting)))
                        widget.setEnabled(settings.value(setting + "_enabled") == "true")
                    elif setting.endswith("_power"):
                        widget.setValue(int(settings.value(setting)))
                    elif "_trig_" in setting:
                        widget.setChecked(settings.value(setting) == "true")
                        widget.setText("Internal" if settings.value(setting) == "true" else "External")
                    elif setting.endswith("_ip") or setting.endswith("_mac"):
                        widget.setText(settings.value(setting))
                    elif setting.endswith("_com"):
                        # TODO (Brad) add dropdown loading
                        pass
                    widget.blockSignals(False)
        
        self.status_update(resp)


    @not_initialized_handler
    async def set_timings_laser(self, laser) -> None:
        timing_inputs = [ii for ii in self.findChildren(QDoubleSpinBox) if f"{laser}_timing" in ii.objectName()]
        timing_inputs.sort(key=lambda x: x.objectName())
        for ind, timing_input in enumerate(timing_inputs):
            # should be sorted to have diode then input
            # want the timing input to be disabled if it is fixed by internal triggering
            # signalling is blocked to not double-trigger
            timing_input.blockSignals(True)
            timing_input.setEnabled(self.lasers[laser]["trig"][ind] == "E")
            if self.lasers[laser]["trig"] == "EI" and bool(ind):
                # qs timing here is set to 179 us later than the diode
                timing_input.setValue(timing_inputs[0].value() + self.lasers[laser]["qsdelay"])
            elif self.lasers[laser]["trig"] == "EE" and not bool(ind):
                # fl timing here is set to 179 us earlier than the qs
                timing_input.setEnabled(False)
                timing_input.setValue(timing_inputs[1].value() - self.lasers[laser]["qsdelay"])
            timing_input.blockSignals(True)
        return f"Timing values set to FL={timing_inputs[0].value()}ns and QS={timing_inputs[1].value()}ns\n"


    def send_timing(self) -> None:
        pass

    @not_initialized_handler
    async def init_laser(self, laser: str) -> None:
        status_text = ""
        try:
            if not ("reader" in self.lasers[laser] or "writer" in self.lasers[laser]):
                reader, writer, resp = await create_reader_writer(
                    host=self.lasers[laser]["HOST"],
                    port=self.lasers[laser]["PORT"],
                    mac=self.lasers[laser]["MAC"],
                )
                status_text += f"{laser}: {resp}\n"
                self.sender().setText("Standby")
                resp = await send_receive(reader, writer, login_command(self.lasers[laser]["MAC"]))
                status_text += f"{laser}: {resp}\n"
                maxcurr = await send_receive(reader, writer, "$MAXCURR ?\n")
                qsdelay = await send_receive(reader, writer, "$QSDELAY ?\n")
                (
                    self.lasers[laser]["reader"],
                    self.lasers[laser]["writer"],
                    self.lasers[laser]["maxcurr"],
                    self.lasers[laser]["qsdelay"],
                ) = reader, writer, float(maxcurr.split(" ")[1]), float(qsdelay.split(" ")[1]) * 1000 # switch qsdelay to ns from us
                status_text += f"{laser}: {maxcurr}\n"
                status_text += f"{laser}: {qsdelay}\n"
            resp = await send_receive(
                self.lasers[laser]["reader"],
                self.lasers[laser]["writer"],
                "$STANDBY\n",
            )
            status_text += f"{laser}: {resp}\n"

        except AttributeError:
            self.sender().setText("Initialize")
            self.sender().setChecked(False)
            status_text += f"{laser}: Could not initialize (power off?)\n"
        finally:
            return status_text

    @not_initialized_handler
    async def send_receive_laser(self, laser: str, command: str) -> str:
        resp = await send_receive(self.lasers[laser]["reader"], self.lasers[laser]["writer"], command)
        print("===========")
        print(resp)
        print("===========")
        return f"{laser}: {resp}\n"
        

    def toggle_button_color(self) -> None:
        self.initialize_button.setStyleSheet(
            "background-color: red" if self.flash_count % 2 else "",
        )

        self.flash_count += 1

        if self.flash_count >= FLASHES:
            self.flash_timer.stop()
            self.initialize_button.setStyleSheet("")
    
    def scroll_to_top(self):
        # Create a cursor at the end of the document and move the cursor there
        cursor = self.status_bar.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.Start)
        self.status_bar.setTextCursor(cursor)
    
    def status_update(self, resp):
        self.status_text = resp + self.status_text
        self.status_bar.setText(self.status_text)
        self.scroll_to_top()


def main() -> None:
    app = QApplication(sys.argv)
    window = LaserGUI()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
