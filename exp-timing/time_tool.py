# time_tool.py
import sys
import time
import numpy as np
import watchdog3
from epics import PV
from typing import Dict, Tuple, List

SYSTEMS = {
    'FS11': {'TTALL': 'XCS:TT:01:TTALL', 'DEV': 'LAS:FS11:VIT:', 'STAGE': 'XCS:LAS:MMN:01.MOVN', 'IPM': 'XCS:SB1:BMMON:SUM'},
    'FS14': {'TTALL': 'XCS:TT:01:TTALL', 'DEV': 'LAS:FS14:VIT:', 'STAGE': 'XCS:LAS:MMN:01.MOVN', 'IPM': 'XCS:SB1:BMMON:SUM'},
    'XPP':  {'TTALL': 'XCS:TT:01:TTALL', 'DEV': 'LAS:FS3:VIT:',  'STAGE': 'XPP:LAS:MMN:16.MOVN', 'IPM': 'XPP:SB2:BMMON:SUM'},
    'XCS':  {'TTALL': 'XCS:TT:01:TTALL', 'DEV': 'LAS:FS4:VIT:',  'STAGE': 'XCS:LAS:MMN:01.MOVN', 'IPM': 'XCS:SB1:BMMON:SUM'},
    'MFX':  {'TTALL': 'MFX:TT:01:TTALL', 'DEV': 'LAS:FS45:VIT:', 'STAGE': 'MFX:LAS:MMN:06.MOVN', 'IPM': 'MFX:DG2:BMMON:SUM'},
    'CXI':  {'TTALL': 'CXI:TT:01:TTALL', 'DEV': 'LAS:FS5:VIT:',  'STAGE': 'CXI:LAS:MMN:09.MOVN', 'IPM': 'CXI:DG2:BMMON:SUM'},
}

TTALL_FIELDS: List[Tuple[int, str]] = [
    (0, 'Pixel Pos'), (1, 'Edge Position'), (2, 'Amplitude'),
    (3, '2nd Amplitude'), (4, 'Background ref'), (5, 'FWHM')
]

def _f(v, d):
    try:
        x = float(v)
        return x if np.isfinite(x) else d
    except Exception:
        return d

class TimeTool:
    """Time Tool using EPICS '.LOW' / '.HIGH' limits embedded in bases; PID drift compensation; Num_Events as float."""

    def __init__(self, system: str = 'FS14'):
        cfg = SYSTEMS.get(system)
        if not cfg:
            raise ValueError(f'Unknown system: {system}')
        print(f'Starting {system} ...')

        self.cfg = cfg
        self.Delay = 0.5
        self.Wait = 60

        # Core PVs
        self.TTALL_PV    = PV(cfg['TTALL']); self.TTALL_PV.wait_for_connection(1.0)
        self.Stage_PV    = PV(cfg['STAGE']); self.Stage_PV.wait_for_connection(1.0)
        self.IPM_PV      = PV(cfg['IPM']);   self.IPM_PV.wait_for_connection(1.0)
        self.TT_Drift_EN = PV(cfg['DEV'] + 'TT_DRIFT_ENABLE'); self.TT_Drift_EN.wait_for_connection(1.0)
        self.TT_Script_EN = PV(cfg['DEV'] + 'matlab:31'); self.TT_Script_EN.wait_for_connection(1.0)

        # Status, flags, tunables, limits, and PID gains embedded in bases
        dev = cfg['DEV']
        bases = {
            'Watchdog': dev+'WATCHDOG',
            'Pixel Pos': dev+'PIX',
            'Edge Position': dev+'FS',
            'Edge_LOW': dev+'FS.LOW',
            'Edge_HIGH': dev+'FS.HIGH',
            'Ave_Edge_Position':      dev+'matlab:30',  # NEW: publish mean edge position (ps)
            'Amplitude': dev+'AMP',
            'Amplitude_LOW': dev+'AMP.LOW',
            'Amplitude_HIGH': dev+'AMP.HIGH',
            '2nd Amplitude': dev+'AMP_SEC',
            'Background ref': dev+'REF',
            'FWHM': dev+'FWHM',
            'FWHM_LOW': dev+'FWHM.LOW',
            'FWHM_HIGH': dev+'FWHM.HIGH',
            'Stage Moving?': dev+'STAGE',
            'IPM': dev+'IPM',
            'IPM_LOW': dev+'IPM.LOW',
            'IPM_HIGH': dev+'IPM.HIGH',
            # PID gains
            'P Gain': dev+'matlab:01',
            'I Gain': dev+'matlab:02',
            'D Gain': dev+'matlab:03',
            # Drift correction value (actuator)
            'Drift Correction Value': dev+'DRIFT_CORRECT_VAL',
            # Flags
            'IPM Good?': dev+'matlab:10',
            'Amplitude Good?': dev+'matlab:11',
            'FWHM Good?': dev+'matlab:12',
            'Good Measurement?': dev+'matlab:13',
            # Tunables
            'Drift_Adjust_Threshold': dev+'matlab:16',
            'Num_Events':             dev+'matlab:19',
            # (legacy) 'Drift Correction Signal' no longer used
            'Drift Correction Signal': dev+'DRIFT_CORRECT_SIG',
        }
        self.drift: Dict[str, PV] = {k: PV(v) for k, v in bases.items()}
        for pv in self.drift.values(): pv.wait_for_connection(1.0)

        # Buffers / watchdog / PID states
        self.Time_Tool_Edges = np.zeros(1, float)  # will resize on first read
        self.W = watchdog3.watchdog(self.drift['Watchdog'])
        self.integral_error = 0.0  # ns·s (integral of ns over seconds)
        self.integral_cap = 0.001  # in ns
        self.prev_error_ns = 0.0
        self._last_pid_t = time.monotonic()
        self.prev_pix_val = 0.0

    def read_write(self):
        """Main loop with .LOW/.HIGH limits from bases, accumulate edges, then PID drift-correct."""
        if self.TT_Script_EN.get(timeout=1.0) != 1:
            return

        # Tunables inline (no defaults dict)
        self.Drift_Adjust_Threshold = _f(self.drift['Drift_Adjust_Threshold'].get(timeout=0.5), 0.0)
        self.Num_Events             = _f(self.drift['Num_Events'].get(timeout=0.5), 1.0)
        num_events_i = max(1, int(round(self.Num_Events)))
        if self.Time_Tool_Edges.size != num_events_i:
            self.Time_Tool_Edges = np.zeros(num_events_i, float)

        # Read limits once per call
        ipm_lo  = self.drift['IPM_LOW'].get(timeout=0.3)
        ipm_hi  = self.drift['IPM_HIGH'].get(timeout=0.3)
        edge_lo = self.drift['Edge_LOW'].get(timeout=0.3)
        edge_hi = self.drift['Edge_HIGH'].get(timeout=0.3)
        amp_lo  = self.drift['Amplitude_LOW'].get(timeout=0.3)
        amp_hi  = self.drift['Amplitude_HIGH'].get(timeout=0.3)
        fwhm_lo = self.drift['FWHM_LOW'].get(timeout=0.3)
        fwhm_hi = self.drift['FWHM_HIGH'].get(timeout=0.3)

        edge_count = 0
        last_good = wd_t = time.monotonic()
        print(f'{time.strftime("%x %X")} - Time Tool Script Enabled \n')

        while edge_count < num_events_i:
            ttall = self.TTALL_PV.get(timeout=1.0)
            stage = self.Stage_PV.get(timeout=1.0)
            ipm   = self.IPM_PV.get(timeout=1.0)

            # unpack TTALL
            pix, edge_pos, amp, amp2, bkg, fwhm = map(float, (ttall[0], ttall[1], ttall[2], ttall[3], ttall[4], ttall[5]))

            # publish raw values
            self.drift['Pixel Pos'].put(pix, wait=True, timeout=1.0)
            self.drift['Edge Position'].put(edge_pos, wait=True, timeout=1.0)
            self.drift['Amplitude'].put(amp, wait=True, timeout=1.0)
            self.drift['2nd Amplitude'].put(amp2, wait=True, timeout=1.0)
            self.drift['Background ref'].put(bkg, wait=True, timeout=1.0)
            self.drift['FWHM'].put(fwhm, wait=True, timeout=1.0)
            self.drift['Stage Moving?'].put(float(stage), wait=True, timeout=1.0)
            self.drift['IPM'].put(float(ipm), wait=True, timeout=1.0)

            # quality checks (exclusive bounds)
            pix_ok   = pix != self.prev_pix_val and pix != 0
            ipm_ok   = (ipm_lo   < ipm      < ipm_hi)
            edge_ok  = (edge_lo  < edge_pos < edge_hi)
            amp_ok   = (amp_lo   < amp      < amp_hi)
            fwhm_ok  = (fwhm_lo  < fwhm     < fwhm_hi)
            stage_ok = not bool(stage)
            good = ipm_ok and edge_ok and amp_ok and pix_ok and fwhm_ok and stage_ok

            # flags
            self.drift['IPM Good?'].put(int(ipm_ok), wait=True, timeout=1.0)
            self.drift['Amplitude Good?'].put(int(amp_ok), wait=True, timeout=1.0)
            self.drift['FWHM Good?'].put(int(fwhm_ok), wait=True, timeout=1.0)
            self.drift['Good Measurement?'].put(int(good), wait=True, timeout=1.0)

            if good:
                print(f'\033[FGood Measurement! - TT Edge Position {edge_pos:.3f} ps    ')
                self.Time_Tool_Edges[edge_count] = edge_pos
                edge_count += 1
                self.prev_pix_val = pix
                last_good = time.monotonic()

            if time.monotonic() - last_good > self.Wait:
                self.prev_pix_val = pix
                print(f"\033[FNo Good Measurement Over {self.Wait} Seconds. "
                      f"Status -> IPM:{ipm_ok}, Edge:{edge_ok}, Amp:{amp_ok}, FWHM:{fwhm_ok}, Pix:{pix_ok}, Stage:{stage_ok}")
                break

            if time.monotonic() - wd_t > 0.5:
                self.W.check()
                wd_t += 0.5
            time.sleep(0.01)

        if edge_count == num_events_i:
            self._apply_drift_correction()

    def _apply_drift_correction(self):
        mean_ps = float(np.mean(self.Time_Tool_Edges))
        print(f'Mean of Edges = {mean_ps:.6f} ps')
        # NEW: publish mean edge position (ps)
        self.drift['Ave_Edge_Position'].put(mean_ps, wait=True, timeout=1.0)
        if self.TT_Drift_EN.get(timeout=1.0) != 1:
            return

        if abs(mean_ps) > self.Drift_Adjust_Threshold:
            old_ns = self.drift['Drift Correction Value'].get(timeout=1.0)
            p_gain = _f(self.drift['P Gain'].get(timeout=1.0), 0.0)
            i_gain = _f(self.drift['I Gain'].get(timeout=1.0), 0.0)
            d_gain = _f(self.drift['D Gain'].get(timeout=1.0), 0.0)

            # error in ns (convert ps -> ns), dt from last correction
            error_ns = mean_ps / 1000.0
            now = time.monotonic()
            dt = now - self._last_pid_t
            if dt <= 0:
                dt = 1e-6  # avoid div-by-zero; tiny dt

            # PID terms
            self.integral_error += error_ns * dt          # integrate error over time (ns·s)
            self.integral_error = np.clip(self.integral_error, -self.integral_cap, self.integral_cap)
            derivative = (error_ns - self.prev_error_ns) / dt

            delta = p_gain * error_ns + i_gain * self.integral_error + d_gain * derivative
            new_ns = old_ns - delta

            print(f'PID -> P:{p_gain:.6f}, I:{i_gain:.6f}, D:{d_gain:.6f}, err(ns):{error_ns:.6f}, integ:{self.integral_error:.6f}, deriv:{derivative:.6f}')
            print(f'Old Drift Correction = {old_ns:.6f} ns, New = {new_ns:.6f} ns, Delta = {delta:.6f} ns')

            self.drift['Drift Correction Value'].put(new_ns, wait=True, timeout=1.0)

            self.prev_error_ns = error_ns
            self._last_pid_t = now
        else:
            print(f'Mean of Edges ({abs(mean_ps):.4f}) < Adjustment Threshold ({self.Drift_Adjust_Threshold}). No Correction Applied.')
            self.integral_error = 0.0           # Optional: reset integrator to avoid windup in deadband

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
            time.sleep(5*tool.Wait)
            tool = TimeTool(system)
            if tool.W.error:
                return

if __name__ == "__main__":
    run()
