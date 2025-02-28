import asyncio
import inspect
import sys
import functools

from constants import FLASHES, MINCURR
from laser_timing import Ui_MainWindow
from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import (
    QApplication,
    QMainWindow,
    QPushButton,
    QTextEdit,
    QTextBrowser,
    QDoubleSpinBox
)
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
            - TODO(Brad): handle timing if in EI, EE, etc mode -- set defaults and disable timing
            input if it is already fixed by the mode
            - TODO(Brad): try with multiple lasers connected
            """

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
                self.status_text = resp + self.status_text
                self.status_bar.setText(self.status_text)
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
            if self.sender().text() == "Enable":
                self.loop.run_until_complete(self.send_receive_laser(l, "$FIRE\n"))
                self.sender().setText("Disable")
            else:
                self.sender().setText("Enable")
                self.loop.run_until_complete(self.send_receive_laser(l, "$STANDBY\n"))

    def initialize(self) -> None:
        l = self.get_laser_name(self.sender())  # noqa: E741
        if l.startswith("v"):
            if self.sender().isChecked():
                self.loop.run_until_complete(self.init_laser(l))
            else:
                self.loop.run_until_complete(self.send_receive_laser(l, "$STOP\n"))

    def set_power_laser(self) -> None:
        resp = ""
        l = self.get_laser_name(self.sender())  # noqa: E741
        if l.startswith("v"):
            self.loop.run_until_complete(
                self.send_receive_laser(
                    l,
                    f"$DCURR {
                        MINCURR
                        + (self.lasers[l]['maxcurr'] - MINCURR) / 100 * self.sender().value()
                    }\n",
                ),
            )
        return resp

    def set_trigger_laser(self, *args, **kwargs) -> None:
        l = self.get_laser_name(self.sender())  # noqa: E741
        trigger_buttons = [
            ii for ii in self.findChildren(QPushButton) if f"{l}_trig_" in ii.objectName()
        ]
        resp = ""
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
        return resp

    def set_timings(self, *args, **kwargs) -> None:
        # TODO For some reason this shit is double-running
        resp = ""
        l = self.get_laser_name(self.sender())  # noqa: E741
        try:
            self.loop.run_until_complete(self.set_timings_laser(l))
        except RuntimeError:
            pass

    @not_initialized_handler
    async def set_timings_laser(self, laser) -> None:
        timing_inputs = [ii for ii in self.findChildren(QDoubleSpinBox) if f"{laser}_timing" in ii.objectName()]
        timing_inputs.sort(key=lambda x: x.objectName())
        for ind, timing_input in enumerate(timing_inputs):
            # should be sorted to have diode then input
            # want the timing input to be disabled if it is fixed by internal triggering
            timing_input.setEnabled(self.lasers[laser]["trig"][ind] == "E")
            if self.lasers[laser]["trig"] == "EI" and bool(ind):
                # qs timing here is set to 179 us later than the diode
                timing_input.setValue(timing_inputs[0].value() + self.lasers[laser]["qsdelay"])
            elif self.lasers[laser]["trig"] == "EE" and not bool(ind):
                # fl timing here is set to 179 us earlier than the qs
                timing_input.setEnabled(False)
                timing_input.setValue(timing_inputs[1].value() - self.lasers[laser]["qsdelay"])
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
            status_text = f"{laser}: Could not initialize (power off?)\n"
        finally:
            return status_text

    @not_initialized_handler
    async def send_receive_laser(self, laser: str, command: str) -> None:
        resp = await send_receive(self.lasers[laser]["reader"], self.lasers[laser]["writer"], command)
        return f"{laser}: {resp}\n"
        

    def toggle_button_color(self) -> None:
        self.initialize_button.setStyleSheet(
            "background-color: red" if self.flash_count % 2 else "",
        )

        self.flash_count += 1

        if self.flash_count >= FLASHES:
            self.flash_timer.stop()
            self.initialize_button.setStyleSheet("")


def main() -> None:
    app = QApplication(sys.argv)
    window = LaserGUI()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
