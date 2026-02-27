# 2602 - Drift Correction GUI for LCLS-I
import sys, argparse
from PyQt5 import QtWidgets, QtCore, QtGui
from PyQt5 import QtWebEngineWidgets

from pydm import Display, PyDMApplication
from pydm.widgets import PyDMLineEdit
from pydm.widgets.channel import PyDMChannel

import epicscorelibs.path.pyepics as _epics_path
import epics

# ---------------- Configuration ----------------
UI_INTERVAL_MS = 500
PRECISION = 3
COL_W = 110

# Colors for state
GREEN = "#3aff3a"; YELLOW = "#ffcc00"; RED = "#ff3a3a"

DEVICE_MAP = {
    "FS11": "LAS:FS11:VIT:", "FS14": "LAS:FS14:VIT:", "FS45": "LAS:FS14:VIT:", "FS15": "LAS:FS14:VIT:",
    "XCS" : "LAS:FS4:VIT:" , "MFX" : "LAS:FS45:VIT:", "CXI" : "LAS:FS5:VIT:" ,
}
DEFAULT_DEVICE = "FS14"

# Ribbon colors by device key (requested mapping)
RIBBON_COLOR_MAP = {
    "FS11": "#00C000",  # Green
    "FS14": "#8D0DFF",  # match XCS
    "FS45": "#FF8700",  # match MFX
    "FS15": "#FF0000",  # match CXI
    "XCS":  "#8D0DFF",  # Purple
    "MFX":  "#FF8700",  # Orange
    "CXI":  "#FF0000",  # Red
}
RIBBON_DEFAULT_COLOR = "#b2bec3"  # fallback

# Reverted mapping per your request
SHUTTER_PV_MAP = {
    "FS11": "PPS:FEH1:6:S6STPRSUM",
    "FS14": "PPS:FEH1:4:S4STPRSUM",
    "FS45": "MFX:DIA:MMS:07:DF",
    "FS15": "PPS:FEH1:5:S5STPRSUM",
    "XCS":  "PPS:FEH1:4:S4STPRSUM",
    "MFX":  "MFX:DIA:MMS:07:DF",
    "CXI":  "PPS:FEH1:5:S5STPRSUM",
}

DISPLAY_PRECISION = { "IPM":1, "FS":2, "AMP":2, "FWHM":1 }
LIMIT_PRECISION   = { "IPM":0, "FWHM":0, "FS":2, "AMP":2 }
LIMITS = list(DISPLAY_PRECISION.keys())

EDITABLE = [
    ("Number of Events","matlab:19"),
    ("Drift Edge Offset","matlab:15"),
    ("P Gain","matlab:01"),
    ("I Gain","matlab:02"),
    ("D Gain","matlab:03"),
]

WARN_RATIO = 0.05  # near-limit threshold

# ---------------- Small UI helpers ----------------
def lbl(text, right=False):
    w = QtWidgets.QLabel(text); w.setStyleSheet("font-weight:bold;")
    if right: w.setAlignment(QtCore.Qt.AlignRight | QtCore.Qt.AlignVCenter)
    return w

def sep():
    f = QtWidgets.QFrame(); f.setFrameShape(QtWidgets.QFrame.HLine); f.setFrameShadow(QtWidgets.QFrame.Sunken)
    return f

EDIT_STYLE = """
    QLineEdit {
        background: #e6e6e6; color: #002a80; padding: 3px 6px;
        border: 1px solid #666; border-radius: 4px;
        selection-background-color: #3399ff; selection-color: white;
    }
    QLineEdit:focus { background: #ffffff; border: 1px solid #3399ff; color: #001a66; }
    QLineEdit:disabled { background: #dcdcdc; color: #888; }
"""

def make_edit(precision: int) -> PyDMLineEdit:
    w = PyDMLineEdit()
    w.precision = precision; w.precisionFromPV = False
    w.setAlignment(QtCore.Qt.AlignRight | QtCore.Qt.AlignVCenter)
    w.setStyleSheet(EDIT_STYLE); w.setFixedWidth(100)
    return w

def compute_uniform_button_width() -> int:
    tmp = QtWidgets.QPushButton()
    fm = tmp.fontMetrics()
    widest = max(fm.horizontalAdvance(s) for s in ("On", "Off", "In", "Out"))
    return widest + 16  # padding consistent across buttons

# ---------------- CLI ----------------
def resolve_device_key(arg: str) -> str:
    if not arg:
        return DEFAULT_DEVICE
    lut = {k.lower(): k for k in DEVICE_MAP}
    key = lut.get(arg.lower())
    if key is None:
        print(f"Unknown device '{arg}'. Options: {', '.join(sorted(DEVICE_MAP))}", file=sys.stderr)
        sys.exit(2)
    return key

def parse_cli(argv):
    p = argparse.ArgumentParser(prog="GUI_TimeTool.py", description="PyDM Drift Correction GUI")
    p.add_argument(
        "device",
        nargs="?",
        default=None,  # None lets us detect "no argument provided"
        help=f"Device key (case-insensitive). Default: {DEFAULT_DEVICE}",
    )
    a = p.parse_args(argv)
    lock_device = (a.device is not None)     # True only if user passed an argument
    dev_key = resolve_device_key(a.device)   # resolves None -> DEFAULT_DEVICE
    return dev_key, lock_device

# ---------------- Channel mixin (removes repeated connect/disconnect) ----------------
class ChannelMixin:
    def __init__(self): self._chan = None
    def set_channel(self, pv, slot):
        if self._chan: self._chan.disconnect()
        self._chan = PyDMChannel(address=f"ca://{pv}", value_slot=slot); self._chan.connect()

# ---------------- PV Display Label ----------------
class SlowLabel(QtWidgets.QLabel, ChannelMixin):
    """
    Display with state colors: GREEN in-range, YELLOW near-limit, RED out-of-range.
    """
    def __init__(self, precision=PRECISION, interval_ms=UI_INTERVAL_MS):
        QtWidgets.QLabel.__init__(self); ChannelMixin.__init__(self)
        self._precision = precision
        self._latest = self._low = self._high = None
        font = self.font(); font.setPointSize(QtWidgets.QApplication.font(self).pointSize()); self.setFont(font)
        self.setAlignment(QtCore.Qt.AlignRight | QtCore.Qt.AlignVCenter)
        self.setFixedWidth(COL_W); self._apply(GREEN)
        t = QtCore.QTimer(self); t.timeout.connect(self._flush); t.start(interval_ms)

    def _apply(self, color: str):
        self.setStyleSheet(f"background:#333;color:{color};padding:5px 12px;border-radius:4px;")

    def _on_value(self, v): self._latest = v
    def _on_low(self, v):   self._low = v
    def _on_high(self, v):  self._high = v

    @property
    def channel(self): return self._chan.address if self._chan else ""

    @channel.setter
    def channel(self, address): self.set_channel(address.replace("ca://",""), self._on_value)

    def assign_limits(self, lo_addr, hi_addr):
        lo = lo_addr.replace("ca://",""); hi = hi_addr.replace("ca://","")
        self._low_chan  = PyDMChannel(address=lo, value_slot=self._on_low)
        self._high_chan = PyDMChannel(address=hi, value_slot=self._on_high)
        self._low_chan.connect(); self._high_chan.connect()

    def _flush(self):
        if self._latest is None: return
        try:
            v = float(self._latest); self.setText(f"{v:.{self._precision}f}")
            color = GREEN
            if self._low is not None and self._high is not None:
                lo, hi = float(self._low), float(self._high)
                if lo > hi: lo, hi = hi, lo
                span = hi - lo
                if not (lo <= v <= hi): color = RED
                elif span > 0 and min(v - lo, hi - v) / span <= WARN_RATIO: color = YELLOW
            self._apply(color)
        except Exception:
            self.setText(str(self._latest))

# ---------------- Other widgets ----------------
class BoolIndicator(QtWidgets.QLabel, ChannelMixin):
    """
    Small round indicator. If green_when_zero=True, green for value==0; else green for value==1.
    """
    def __init__(self, pv, green_when_zero=False):
        QtWidgets.QLabel.__init__(self); ChannelMixin.__init__(self)
        self._green_when_zero = green_when_zero
        self.setFixedSize(18, 18); self.setStyleSheet("border-radius:9px;background:red;")
        self.set_pv(pv)

    def set_pv(self, pv): self.set_channel(pv, self.update_color)

    def update_color(self, value):
        try:
            v = int(value)
            col = "green" if ((v == 0) if self._green_when_zero else (v == 1)) else "red"
        except Exception:
            col = "red"
        self.setStyleSheet(f"border-radius:9px;background:{col};")

class ToggleButton(QtWidgets.QPushButton, ChannelMixin):
    """Uniform-width button that toggles a 0/1 PV."""
    def __init__(self, pv, width):
        QtWidgets.QPushButton.__init__(self, "Off"); ChannelMixin.__init__(self)
        self._pv = pv; self.setFixedWidth(width); self.set_pv(pv); self.clicked.connect(self.toggle)

    def set_pv(self, pv): self._pv = pv; self.set_channel(pv, self.update_state)

    def update_state(self, v):
        try: self.setText("On" if int(v) == 1 else "Off")
        except Exception: self.setText("Off")

    def toggle(self):
        if not epics:
            QtWidgets.QMessageBox.warning(self, "EPICS unavailable", "pyepics not available."); return
        epics.caput(self._pv, 0 if self.text() == "On" else 1, wait=False)

class StatusButton(QtWidgets.QPushButton, ChannelMixin):
    """
    Read-only shutter status that looks enabled (no grey).
    Shows 'Out' when PV==0 and 'In' otherwise. Clicks are ignored.
    """
    def __init__(self, pv, width):
        QtWidgets.QPushButton.__init__(self, "Out"); ChannelMixin.__init__(self)
        self.setFixedWidth(width); self.setCursor(QtCore.Qt.ArrowCursor); self.setToolTip("Shutter status (read-only)")
        self.set_pv(pv)

    def mousePressEvent(self, e: QtGui.QMouseEvent): e.ignore()  # ignore clicks

    def set_pv(self, pv): self.set_channel(pv, self.update_state)

    def update_state(self, value):
        try: self.setText("Out" if int(value) == 0 else "In")
        except Exception: self.setText("Out")

# ---------------- Main Display ----------------
class LimitsScreen(Display):
    def __init__(self, parent=None, args=None, initial_device=DEFAULT_DEVICE, lock_device=False):
        super().__init__(parent, args)
        self.setWindowTitle("LCLS-I Drift Correction")
        self._lock_device = lock_device

        vbox = QtWidgets.QVBoxLayout(self)
        vbox.setContentsMargins(8, 8, 8, 8)  # helps rounded corners show cleanly
        vbox.setSpacing(8)

        self._button_width = compute_uniform_button_width()

        # Create ribbon (also creates self.dev_combo)
        self.ribbon = self._make_ribbon()

        # - If NOT locked, show dropdown row on top, then ribbon below.
        # - If locked, show only ribbon.
        if not self._lock_device:
            selector = QtWidgets.QHBoxLayout()
            selector.addWidget(lbl("Hutch"))
            selector.addWidget(self.dev_combo)
            selector.addStretch()
            vbox.addLayout(selector)

        vbox.addWidget(self.ribbon)
        vbox.addWidget(sep())

        # Top controls
        drift = QtWidgets.QGridLayout()
        drift.addWidget(lbl("Apply Drift Correction?", True), 0, 0)
        self.drift_btn = ToggleButton("LAS:FS14:VIT:DRIFT_CORRECT_GAIN", self._button_width); drift.addWidget(self.drift_btn, 0, 1)
        self.drift_ind = BoolIndicator("LAS:FS14:VIT:DRIFT_CORRECT_GAIN"); drift.addWidget(self.drift_ind, 0, 2)

        drift.addWidget(lbl("Drift Script Enabled?", True), 1, 0)
        self.script_btn = ToggleButton("LAS:FS14:VIT:matlab:31", self._button_width); drift.addWidget(self.script_btn, 1, 1)
        self.script_ind = BoolIndicator("LAS:FS14:VIT:matlab:31"); drift.addWidget(self.script_ind, 1, 2)

        drift.addWidget(lbl("X-ray Shutter Status", True), 2, 0)
        self.shutter_btn = StatusButton("PPS:FEH1:6:S6STPRSUM", self._button_width); drift.addWidget(self.shutter_btn, 2, 1)
        self.shutter_ind = BoolIndicator("PPS:FEH1:6:S6STPRSUM", green_when_zero=True); drift.addWidget(self.shutter_ind, 2, 2)

        vbox.addLayout(drift); vbox.addWidget(sep())

        # Indicators
        ind = QtWidgets.QGridLayout()
        ind.addWidget(lbl("Time Tool Watchdog", True), 0, 2)
        self.watchdog = SlowLabel(precision=0); ind.addWidget(self.watchdog, 0, 3)
        ind.addWidget(lbl("Current Drift Correction", True), 1, 2)
        self.drift_val = SlowLabel(precision=6); ind.addWidget(self.drift_val, 1, 3)
        ind.addWidget(lbl("Average Edge Position", True), 2, 2)
        self.avg_value = SlowLabel(precision=PRECISION); ind.addWidget(self.avg_value, 2, 3)
        vbox.addLayout(ind); vbox.addWidget(sep())

        # Limits grid
        grid = QtWidgets.QGridLayout()
        grid.addWidget(lbl(""), 0, 0); grid.addWidget(lbl("Value"), 0, 1)
        grid.addWidget(lbl("Min", True), 0, 2); grid.addWidget(lbl("Max", True), 0, 3)

        self.value_widgets, self.low_widgets, self.high_widgets = {}, {}, {}
        for r, name in enumerate(LIMITS, 1):
            grid.addWidget(lbl(name), r, 0)
            val = SlowLabel(precision=DISPLAY_PRECISION[name]); self.value_widgets[name] = val; grid.addWidget(val, r, 1)
            low = make_edit(LIMIT_PRECISION[name]); high = make_edit(LIMIT_PRECISION[name])
            self.low_widgets[name], self.high_widgets[name] = low, high
            grid.addWidget(low, r, 2); grid.addWidget(high, r, 3)

        vbox.addLayout(grid); vbox.addWidget(sep())

        # Other editable PVs
        edits = QtWidgets.QGridLayout()
        edits.addWidget(lbl(""), 0, 0); edits.addWidget(lbl(""), 0, 1); edits.addWidget(lbl("Settings", True), 0, 3)
        self.editable_edits = {}
        for r, (desc, suf) in enumerate(EDITABLE, 1):
            edits.addWidget(lbl(desc, True), r, 2)
            w = make_edit(0 if desc == "Number of Events" else PRECISION); self.editable_edits[suf] = w
            edits.addWidget(w, r, 3)
        vbox.addLayout(edits); vbox.addStretch()

        # Initialize selection and channels
        self.dev_combo.setCurrentText(initial_device)
        self.update_channels(initial_device)

        # If locked, prevent accidental changes via code/UI
        if self._lock_device:
            self.dev_combo.setEnabled(False)

    def _make_ribbon(self) -> QtWidgets.QWidget:
        """
        A simple colored ribbon with centered device label.
        Same ribbon used in both locked and unlocked modes.
        """
        self.dev_combo = QtWidgets.QComboBox()
        self.dev_combo.addItems(DEVICE_MAP)
        self.dev_combo.currentTextChanged.connect(self.update_channels)

        ribbon = QtWidgets.QFrame()
        ribbon.setFixedHeight(46)
        ribbon.setStyleSheet(self._ribbon_style(RIBBON_DEFAULT_COLOR))

        layout = QtWidgets.QHBoxLayout(ribbon)
        layout.setContentsMargins(0, 0, 0, 0)

        self.dev_label = QtWidgets.QLabel(DEFAULT_DEVICE)
        self.dev_label.setAlignment(QtCore.Qt.AlignCenter)

        font = self.dev_label.font()
        font.setPointSize(font.pointSize() + 8)
        font.setBold(True)
        self.dev_label.setFont(font)

        self.dev_label.setStyleSheet(
            """
            QLabel {
                color: #000000;
                background: transparent;
                border: none;
                padding: 0px;
                margin: 0px;
            }
            """
        )
        self.dev_label.setFocusPolicy(QtCore.Qt.NoFocus)

        layout.addWidget(self.dev_label, 1)
        return ribbon

    def _ribbon_style(self, color_hex: str) -> str:
        return f"""
            QFrame {{
                background: {color_hex};
                border: none;
                border-radius: 10px;
            }}
        """

    def _set_ribbon_color(self, dev_key: str):
        color = RIBBON_COLOR_MAP.get(dev_key, RIBBON_DEFAULT_COLOR)
        self.ribbon.setStyleSheet(self._ribbon_style(color))

    def _prefix(self):
        base = DEVICE_MAP[self.dev_combo.currentText()]
        return base if base.endswith(":") else base + ":"

    def update_channels(self, _):
        dev_key = self.dev_combo.currentText()
        pref = self._prefix()

        # Ribbon updates
        self.dev_label.setText(dev_key)
        self._set_ribbon_color(dev_key)

        self.watchdog.channel  = f"ca://{pref}WATCHDOG"
        self.avg_value.channel = f"ca://{pref}matlab:18"
        self.drift_val.channel = f"ca://{pref}DRIFT_CORRECT_VAL"

        for name in LIMITS:
            base = f"ca://{pref}{name}"
            self.value_widgets[name].channel = base
            self.value_widgets[name].assign_limits(f"{base}.LOW", f"{base}.HIGH")
            self.low_widgets[name].channel  = f"{base}.LOW"
            self.high_widgets[name].channel = f"{base}.HIGH"

        for suf, w in self.editable_edits.items():
            w.channel = f"ca://{pref}{suf}"

        driftPV, scriptPV = f"{pref}DRIFT_CORRECT_GAIN", f"{pref}matlab:31"
        self.drift_btn.set_pv(driftPV); self.drift_ind.set_pv(driftPV)
        self.script_btn.set_pv(scriptPV); self.script_ind.set_pv(scriptPV)

        shutter_pv = SHUTTER_PV_MAP.get(dev_key, "PPS:FEH1:6:S6STPRSUM")
        self.shutter_btn.set_pv(shutter_pv); self.shutter_ind.set_pv(shutter_pv)

    def ui_filename(self): return None

# ---------------- Entrypoint ----------------
if __name__ == "__main__":
    dev, locked = parse_cli(sys.argv[1:])
    QtCore.QCoreApplication.setAttribute(QtCore.Qt.AA_ShareOpenGLContexts, True)
    app = PyDMApplication(use_main_window=False, ui_file=None)
    w = LimitsScreen(initial_device=dev, lock_device=locked)
    w.show()
    sys.exit(app.exec_())
