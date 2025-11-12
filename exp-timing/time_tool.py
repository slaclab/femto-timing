# 251110 - Time tool code, try to make it more readable switch to epics library and tested with this code.
# time_tool.py
import time
import numpy as np
from epics import PV
import sys
from typing import Dict, Tuple, List
import watchdog3

# Configuration
SYSTEMS = {
    'FS11': {'TTALL': 'XCS:TT:01:TTALL', 'DEV': 'LAS:FS11:VIT:', 'STAGE': 'XCS:LAS:MMN:01.MOVN', 'IPM': 'XCS:SB1:BMMON:SUM'},
    'FS14': {'TTALL': 'CXI:TT:01:TTALL', 'DEV': 'LAS:FS14:VIT:', 'STAGE': 'CXI:LAS:MMN:09.MOVN', 'IPM': 'CXI:DG2:BMMON:SUM'},
    'XPP':  {'TTALL': 'XCS:TT:01:TTALL', 'DEV': 'LAS:FS3:VIT:',  'STAGE': 'XPP:LAS:MMN:16.MOVN', 'IPM': 'XPP:SB2:BMMON:SUM'},
    'XCS':  {'TTALL': 'XCS:TT:01:TTALL', 'DEV': 'LAS:FS4:VIT:',  'STAGE': 'XCS:LAS:MMN:01.MOVN', 'IPM': 'XCS:SB1:BMMON:SUM'},
    'MFX':  {'TTALL': 'MFX:TT:01:TTALL', 'DEV': 'LAS:FS45:VIT:', 'STAGE': 'MFX:LAS:MMN:06.MOVN', 'IPM': 'MFX:DG2:BMMON:SUM'},
    'CXI':  {'TTALL': 'CXI:TT:01:TTALL', 'DEV': 'LAS:FS5:VIT:',  'STAGE': 'CXI:LAS:MMN:09.MOVN', 'IPM': 'CXI:DG2:BMMON:SUM'},
}

TTALL_FIELDS: List[Tuple[int, str]] = [(0, 'Pixel Pos'), (1, 'Edge Position'), (2, 'Amplitude'),
    (3, '2nd Amplitude'), (4, 'Background ref'), (5, 'FWHM')]

# TimeTool Class
class TimeTool:
    """Handles Time Tool operations for drift correction and measurement validation."""

    def __init__(self, system: str = 'FS14'):
        # Thresholds
        self.IPM_Threshold = 500.0
        self.Amplitude_Threshold = 0.02
        self.Drift_Adjust_Threshold = 0.05
        self.FWHM_Low = 30.0
        self.FWHM_High = 250.0
        self.Num_Events = 61
        self.Delay = 0.5
        self.Time_Tool_Edges = np.zeros(self.Num_Events, dtype=float)

        cfg = SYSTEMS.get(system)
        if not cfg:
            raise ValueError(f'Unknown system: {system}')
        print(f'Starting {system} ...')

        self._connect_pvs(cfg)
        self.W = watchdog3.watchdog(self.drift_correct['Watchdog'])

    def _connect_pvs(self, cfg: Dict[str, str]):
        """Connect to all required PVs."""
        self.TTALL_PV = PV(cfg['TTALL']); self.TTALL_PV.wait_for_connection(timeout=1.0)
        self.Stage_PV = PV(cfg['STAGE']); self.Stage_PV.wait_for_connection(timeout=1.0)
        self.IPM_PV = PV(cfg['IPM']); self.IPM_PV.wait_for_connection(timeout=1.0)
        self.TT_Script_EN = PV(cfg['DEV'] + 'matlab:31'); self.TT_Script_EN.wait_for_connection(timeout=1.0)

        # Drift correction PVs
        bases = {
            'Watchdog': cfg['DEV']+'WATCHDOG',
            'Pixel Pos': cfg['DEV']+'PIX',
            'Edge Position': cfg['DEV']+'FS',
            'Amplitude': cfg['DEV']+'AMP',
            '2nd Amplitude': cfg['DEV']+'AMP_SEC',
            'Background ref': cfg['DEV']+'REF',
            'FWHM': cfg['DEV']+'FWHM',
            'Stage Moving?': cfg['DEV']+'STAGE',
            'IPM': cfg['DEV']+'IPM',
            'Drift Correction Signal': cfg['DEV']+'DRIFT_CORRECT_SIG',
            'Drift Correction Value': cfg['DEV']+'DRIFT_CORRECT_VAL',
            'IPM Good?': cfg['DEV']+'matlab:11',
            'Amplitude Good?': cfg['DEV']+'matlab:12',
            'FWHM Good?': cfg['DEV']+'matlab:13',
            'Good TT Measurement?': cfg['DEV']+'matlab:14',
        }

        self.drift_correct: Dict[str, PV] = {}
        for name, base in bases.items():
            pv = PV(base); pv.wait_for_connection(timeout=1.0)
            self.drift_correct[name] = pv

    def read_write(self):
        """Main loop for reading PVs and applying drift correction."""
        self.TT_Script_EN.get(timeout=1.0)
        if self.TT_Script_EN.value != 1:
            return

        print(f'{time.strftime("%x %X")} - Time Tool Script Enabled \n')
        edge_count = 0
        prev_pix_val = 0
        last_good = time.monotonic()
        wd_times = last_good

        while edge_count < self.Num_Events:
            ttall = self.TTALL_PV.get(timeout=1.0)
            stage = self.Stage_PV.get(timeout=1.0)
            ipm = self.IPM_PV.get(timeout=1.0)

            # Update PVs
            for idx, name in TTALL_FIELDS:
                self.drift_correct[name].put(float(ttall[idx]), wait=True, timeout=1.0)
            self.drift_correct['Stage Moving?'].put(float(stage), wait=True, timeout=1.0)
            self.drift_correct['IPM'].put(float(ipm), wait=True, timeout=1.0)

            # Validate
            ipm_ok = ipm > self.IPM_Threshold
            amp_ok = ttall[2] > self.Amplitude_Threshold
            pix_ok = ttall[0] != prev_pix_val and ttall[0] != 0
            fwhm_ok = self.FWHM_Low < ttall[5] < self.FWHM_High
            stage_ok = not bool(stage)
            good = all([ipm_ok, amp_ok, pix_ok, fwhm_ok, stage_ok])

            # Update flags
            self.drift_correct['IPM Good?'].put(int(ipm_ok), wait=True, timeout=1.0)
            self.drift_correct['Amplitude Good?'].put(int(amp_ok), wait=True, timeout=1.0)
            self.drift_correct['FWHM Good?'].put(int(fwhm_ok), wait=True, timeout=1.0)
            self.drift_correct['Good TT Measurement?'].put(int(good), wait=True, timeout=1.0)

            if good:
                edge = float(ttall[1])
                print(f'\033[FGood Measurement! - TT Edge Position {edge:.3f} ps    ')
                self.Time_Tool_Edges[edge_count] = edge
                edge_count += 1
                prev_pix_val = ttall[0]
                last_good = time.monotonic()

            if time.monotonic() - last_good > 60:
                print(f"\033[FNo Good Measurement Over One Minute. Status -> IPM:{ipm_ok}, Amp:{amp_ok}, FWHM:{fwhm_ok}, Pix:{pix_ok}, Stage:{stage_ok}")
                break

            if time.monotonic() - wd_times > 0.5:
                self.W.check()
                wd_times += 0.5
            time.sleep(0.01)

        if edge_count == self.Num_Events:
            self._apply_drift_correction()

    def _apply_drift_correction(self):
        """Apply drift correction if needed."""
        edge_mean = np.mean(self.Time_Tool_Edges)
        print(f'Mean of Edges = {edge_mean:.6f} ps')

        if abs(edge_mean) > self.Drift_Adjust_Threshold:
            old_val = self.drift_correct['Drift Correction Value'].get(timeout=1.0)
            p_gain = self.drift_correct['Drift Correction Signal'].get(timeout=1.0)
            new_val = -p_gain * (edge_mean / 1000)  # ps -> ns
            # new_val = old_val - p_gain * (edge_mean / 1000)
            print(f'Old Drift Correction = {old_val:.6f} ns, New = {new_val:.6f} ns')
            self.drift_correct['Drift Correction Value'].put(new_val, wait=True, timeout=1.0)
        else:
            print(f'Mean of Edges ({abs(edge_mean):.4f}) < Adjustment Threshold ({self.Drift_Adjust_Threshold}). No Correction Applied.')

# Main Entry
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
            tool = TimeTool(system)
            if tool.W.error:
                return

if __name__ == "__main__":
    run()
