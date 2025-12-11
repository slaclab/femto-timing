# 251112 - Time tool code from epic.py, try to make it more readable switch to epics library and change parameters live.
# time_tool.py
import sys
import time
import numpy as np
import watchdog3
from epics import PV
from typing import Dict, Tuple, List

SYSTEMS = {
    'FS11': {'TTALL': 'XCS:TT:01:TTALL', 'DEV': 'LAS:FS11:VIT:', 'STAGE': 'XCS:LAS:MMN:01.MOVN', 'IPM': 'XCS:SB1:BMMON:SUM'},
    'FS14': {'TTALL': 'CXI:TT:01:TTALL', 'DEV': 'LAS:FS14:VIT:', 'STAGE': 'CXI:LAS:MMN:09.MOVN', 'IPM': 'CXI:DG2:BMMON:SUM'},
    'XPP':  {'TTALL': 'XCS:TT:01:TTALL', 'DEV': 'LAS:FS3:VIT:',  'STAGE': 'XPP:LAS:MMN:16.MOVN', 'IPM': 'XPP:SB2:BMMON:SUM'},
    'XCS':  {'TTALL': 'XCS:TT:01:TTALL', 'DEV': 'LAS:FS4:VIT:',  'STAGE': 'XCS:LAS:MMN:01.MOVN', 'IPM': 'XCS:SB1:BMMON:SUM'},
    'MFX':  {'TTALL': 'MFX:TT:01:TTALL', 'DEV': 'LAS:FS45:VIT:', 'STAGE': 'MFX:LAS:MMN:06.MOVN', 'IPM': 'MFX:DG2:BMMON:SUM'},
    'CXI':  {'TTALL': 'CXI:TT:01:TTALL', 'DEV': 'LAS:FS5:VIT:',  'STAGE': 'CXI:LAS:MMN:09.MOVN', 'IPM': 'CXI:DG2:BMMON:SUM'},
}

TTALL_FIELDS: List[Tuple[int, str]] = [ (0, 'Pixel Pos'), (1, 'Edge Position'), (2, 'Amplitude'), (3, '2nd Amplitude'), (4, 'Background ref'), (5, 'FWHM')]

PARAM_DEFAULTS = {
    'IPM_Threshold': 500.0,
    'Amplitude_Threshold': 0.02,
    'Drift_Adjust_Threshold': 0.05,
    'FWHM_Low': 30.0,
    'FWHM_High': 250.0,
    'Num_Events': 61.0,
}
PARAM_IDS = {
    'IPM_Threshold':          14,
    'Amplitude_Threshold':    15,
    'Drift_Adjust_Threshold': 16,
    'FWHM_Low':               17,
    'FWHM_High':              18,
    'Num_Events':             19,
}

def _f(v, d):  # safe float
    try:
        x = float(v)
        return x if np.isfinite(x) else d
    except Exception:
        return d

class TimeTool:
    """Time Tool with PV-driven thresholds (compact), Num_Events as float."""

    def __init__(self, system: str = 'FS14'):
        cfg = SYSTEMS.get(system)
        if not cfg:
            raise ValueError(f'Unknown system: {system}')
        print(f'Starting {system} ...')

        self.cfg = cfg
        self.Delay = 0.5

        # Core PVs
        self.TTALL_PV   = PV(cfg['TTALL']); self.TTALL_PV.wait_for_connection(1.0)
        self.Stage_PV   = PV(cfg['STAGE']); self.Stage_PV.wait_for_connection(1.0)
        self.IPM_PV     = PV(cfg['IPM']);   self.IPM_PV.wait_for_connection(1.0)
        self.TT_Drift_EN = PV(cfg['DEV'] + 'TT_DRIFT_ENABLE'); self.TT_Drift_EN.wait_for_connection(1.0)
        self.TT_Script_EN = PV(cfg['DEV'] + 'matlab:31'); self.TT_Script_EN.wait_for_connection(1.0)

        # Status & control PVs
        dev = cfg['DEV']
        bases = {
            'Watchdog': dev+'WATCHDOG', 'Pixel Pos': dev+'PIX', 'Edge Position': dev+'FS',
            'Amplitude': dev+'AMP', '2nd Amplitude': dev+'AMP_SEC', 'Background ref': dev+'REF',
            'FWHM': dev+'FWHM', 'Stage Moving?': dev+'STAGE', 'IPM': dev+'IPM',
            'Drift Correction Signal': dev+'DRIFT_CORRECT_SIG',
            'Drift Correction Value': dev+'DRIFT_CORRECT_VAL',
            'IPM Good?': dev+'matlab:10', 'Amplitude Good?': dev+'matlab:11',
            'FWHM Good?': dev+'matlab:12', 'Good Measurement?': dev+'matlab:13',
        }
        self.drift: Dict[str, PV] = {k: PV(v) for k, v in bases.items()}
        for pv in self.drift.values(): pv.wait_for_connection(1.0)

        # Parameter PVs (push defaults if unset)
        self.param_pvs: Dict[str, PV] = {}
        for name, idx in PARAM_IDS.items():
            pv = PV(f"{dev}matlab:{idx}")
            pv.wait_for_connection(1.0)
            self.param_pvs[name] = pv
            if pv.get(timeout=0.2) == 0:
                pv.put(PARAM_DEFAULTS[name], wait=False)

        # Load parameters and init buffers / watchdog
        self._read_params()
        num_events_i = max(1, int(round(self.Num_Events)))  # <- cast here
        self.Time_Tool_Edges = np.zeros(num_events_i, float)
        self.W = watchdog3.watchdog(self.drift['Watchdog'])

    def _read_params(self):
        """Refresh parameters from PVs (with safe float fallbacks); Num_Events stays float."""
        g = lambda k: self.param_pvs[k].get(timeout=0.5)
        self.IPM_Threshold          = _f(g('IPM_Threshold'),          PARAM_DEFAULTS['IPM_Threshold'])
        self.Amplitude_Threshold    = _f(g('Amplitude_Threshold'),    PARAM_DEFAULTS['Amplitude_Threshold'])
        self.Drift_Adjust_Threshold = _f(g('Drift_Adjust_Threshold'), PARAM_DEFAULTS['Drift_Adjust_Threshold'])
        self.FWHM_Low               = _f(g('FWHM_Low'),               PARAM_DEFAULTS['FWHM_Low'])
        self.FWHM_High              = _f(g('FWHM_High'),              PARAM_DEFAULTS['FWHM_High'])
        self.Num_Events             = _f(g('Num_Events'),             PARAM_DEFAULTS['Num_Events'])  # <- float

    def read_write(self):
        """Main loop: read PVs, validate, accumulate, correct drift."""
        if self.TT_Script_EN.get(timeout=1.0) != 1:
            return

        # allow live tuning
        self._read_params()
        num_events_i = max(1, int(round(self.Num_Events)))  # <- cast when using
        if self.Time_Tool_Edges.size != num_events_i:
            self.Time_Tool_Edges = np.zeros(num_events_i, float)

        print(f'{time.strftime("%x %X")} - Time Tool Script Enabled \n')
        edge_count, prev_pix_val = 0, 0
        last_good = wd_t = time.monotonic()

        while edge_count < num_events_i:  # <- integer loop bound
            ttall = self.TTALL_PV.get(timeout=1.0)
            stage = self.Stage_PV.get(timeout=1.0)
            ipm   = self.IPM_PV.get(timeout=1.0)

            # publish raw values
            for idx, name in TTALL_FIELDS:
                self.drift[name].put(float(ttall[idx]), wait=True, timeout=1.0)
            self.drift['Stage Moving?'].put(float(stage), wait=True, timeout=1.0)
            self.drift['IPM'].put(float(ipm), wait=True, timeout=1.0)

            # quality checks
            ipm_ok  = ipm > self.IPM_Threshold
            amp_ok  = ttall[2] > self.Amplitude_Threshold
            pix_ok  = ttall[0] != prev_pix_val and ttall[0] != 0
            fwhm_ok = self.FWHM_Low < ttall[5] < self.FWHM_High
            stage_ok = not bool(stage)
            good = ipm_ok and amp_ok and pix_ok and fwhm_ok and stage_ok

            # flags
            self.drift['IPM Good?'].put(int(ipm_ok), wait=True, timeout=1.0)
            self.drift['Amplitude Good?'].put(int(amp_ok), wait=True, timeout=1.0)
            self.drift['FWHM Good?'].put(int(fwhm_ok), wait=True, timeout=1.0)
            self.drift['Good Measurement?'].put(int(good), wait=True, timeout=1.0)

            if good:
                edge = float(ttall[1])
                print(f'\033[FGood Measurement! - TT Edge Position {edge:.3f} ps    ')
                self.Time_Tool_Edges[edge_count] = edge
                edge_count += 1
                prev_pix_val = ttall[0]
                last_good = time.monotonic()

            if time.monotonic() - last_good > 60:
                print(f"\033[FNo Good Measurement Over One Minute. "
                      f"Status -> IPM:{ipm_ok}, Amp:{amp_ok}, FWHM:{fwhm_ok}, Pix:{pix_ok}, Stage:{stage_ok}")
                break

            if time.monotonic() - wd_t > 0.5:
                self.W.check()
                wd_t += 0.5
            time.sleep(0.01)

        if edge_count == num_events_i:  # <- compare with int
            self._apply_drift_correction()

    def _apply_drift_correction(self):
        mean_ps = float(np.mean(self.Time_Tool_Edges))# - 0.5 # Middle of the time tool is 0.5?
        print(f'Mean of Edges = {mean_ps:.6f} ps')
        if self.TT_Drift_EN.get(timeout=1.0) != 1:
            return
        if abs(mean_ps) > self.Drift_Adjust_Threshold:
            old_ns = self.drift['Drift Correction Value'].get(timeout=1.0)
            p_gain = self.drift['Drift Correction Signal'].get(timeout=1.0)
            # new_ns = -p_gain * (mean_ps / 1000.0)  # ps -> ns
            new_ns = old_ns - p_gain * (mean_ps / 1000.0)
            print(f'Old Drift Correction = {old_ns:.6f} ns, New = {new_ns:.6f} ns')
            self.drift['Drift Correction Value'].put(new_ns, wait=True, timeout=1.0)
        else:
            print(f'Mean of Edges ({abs(mean_ps):.4f}) < Adjustment Threshold ({self.Drift_Adjust_Threshold}). No Correction Applied.')

def run():
    system = sys.argv[1] if len(sys.argv) > 1 else 'FS14'
    tool = TimeTool(system)
    while tool.W.error == 0:
        tool.W.check()
        time.sleep(tool.Delay)
        try:
            tool.read_write()
        except Exception as e:
            print(f'Crashed: {e}, restarting')
            time.sleep(90)
            tool = TimeTool(system)
            if tool.W.error:
                return

if __name__ == "__main__":
    run()
