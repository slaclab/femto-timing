# 2602 - time_tool.py
import sys
import time
import numpy as np
import watchdog3
from epics import PV
from typing import Dict, Tuple, List

SYSTEMS = {
    'FS11': {'TTALL': 'XCS:TT:01:TTALL',     'DEV': 'LAS:FS11:VIT:', 'STAGE': 'XCS:LAS:MMN:01.MOVN', 'IPM': 'XCS:SB1:BMMON:SUM', 'SHUTTER': 'PPS:FEH1:5:S5STPRSUM'},
    'FS14': {'TTALL': 'XCS:TT:01:TTALL',     'DEV': 'LAS:FS14:VIT:', 'STAGE': 'XCS:LAS:MMN:01.MOVN', 'IPM': 'XCS:SB1:BMMON:SUM', 'SHUTTER': 'PPS:FEH1:4:S4STPRSUM'},
    'FS45': {'TTALL': 'MFX:ALV:04:TT:TTALL', 'DEV': 'LAS:FS14:VIT:', 'STAGE': 'MFX:LAS:MMN:06.MOVN', 'IPM': 'MFX:DG2:BMMON:SUM', 'SHUTTER': 'MFX:DIA:MMS:07:DF'},
    'FS15': {'TTALL': 'CXI:TT:01:TTALL',     'DEV': 'LAS:FS14:VIT:', 'STAGE': 'CXI:LAS:MMN:09.MOVN', 'IPM': 'CXI:DG2:BMMON:SUM', 'SHUTTER': 'PPS:FEH1:5:S5STPRSUM'},
    'XPP':  {'TTALL': 'XCS:TT:01:TTALL',     'DEV': 'LAS:FS3:VIT:',  'STAGE': 'XPP:LAS:MMN:16.MOVN', 'IPM': 'XPP:SB2:BMMON:SUM', 'SHUTTER': 'PPS:FEH1:5:S5STPRSUM'},
    'XCS':  {'TTALL': 'XCS:TT:01:TTALL',     'DEV': 'LAS:FS4:VIT:',  'STAGE': 'XCS:LAS:MMN:01.MOVN', 'IPM': 'XCS:SB1:BMMON:SUM', 'SHUTTER': 'PPS:FEH1:4:S4STPRSUM'},
    'MFX':  {'TTALL': 'MFX:ALV:04:TT:TTALL', 'DEV': 'LAS:FS45:VIT:', 'STAGE': 'MFX:LAS:MMN:06.MOVN', 'IPM': 'MFX:DG2:BMMON:SUM', 'SHUTTER': 'MFX:DIA:MMS:07:DF'},
    'CXI':  {'TTALL': 'CXI:TT:01:TTALL',     'DEV': 'LAS:FS5:VIT:',  'STAGE': 'CXI:LAS:MMN:09.MOVN', 'IPM': 'CXI:DG2:BMMON:SUM', 'SHUTTER': 'PPS:FEH1:5:S5STPRSUM'},
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
    """Time Tool using EPICS '.LOW' / '.HIGH' limits embedded in bases; PID drift compensation."""
    def __init__(self, system: str = 'FS14'):
        cfg = SYSTEMS.get(system)
        if not cfg:
            raise ValueError(f'Unknown system: {system}')
        print(f'Starting {system} ...')

        self.cfg = cfg
        self.Delay = 0.5
        self.Wait = 60

        # Core PVs
        self.TTALL_PV     = PV(cfg['TTALL']); self.TTALL_PV.wait_for_connection(1.0)
        self.Stage_PV     = PV(cfg['STAGE']); self.Stage_PV.wait_for_connection(1.0)
        self.IPM_PV       = PV(cfg['IPM']);   self.IPM_PV.wait_for_connection(1.0)
        self.Shutter_PV   = PV(cfg['SHUTTER']); self.Shutter_PV.wait_for_connection(1.0)
        self.TT_Drift_EN  = PV(cfg['DEV'] + 'TT_DRIFT_ENABLE'); self.TT_Drift_EN.wait_for_connection(1.0)
        self.TT_Script_EN = PV(cfg['DEV'] + 'matlab:31'); self.TT_Script_EN.wait_for_connection(1.0)

        # Status, flags, tunables, limits, and PID gains embedded in bases
        dev = cfg['DEV']
        bases = {
            'Watchdog': dev+'WATCHDOG',
            'Pixel Pos': dev+'PIX',
            'Edge Position': dev+'FS',
            'Edge_LOW': dev+'FS.LOW',
            'Edge_HIGH': dev+'FS.HIGH',
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
            # Tunables
            'Drift_Edge_Offset':            dev+'matlab:15',
            'Drift_Adjust_Threshold':       dev+'matlab:16',
            'Drift_Std_Dev_Edge_Position':  dev+'matlab:17',
            'Drift_Ave_Edge_Position':      dev+'matlab:18',
            'Drift_Number_Events':          dev+'matlab:19',
            # (legacy) 'Drift Correction Signal' no longer used
            'Drift Correction Signal': dev+'DRIFT_CORRECT_SIG',
        }
        self.drift: Dict[str, PV] = {k: PV(v) for k, v in bases.items()}
        for pv in self.drift.values(): pv.wait_for_connection(1.0)
        self.drift['Watchdog'].put(0, timeout=1.0, wait=True)         # Restart Watchdog counts

        # Buffers / watchdog / PID states
        self.Time_Tool_Edges = np.zeros(1, float)  # will resize on first read
        self.W = watchdog3.watchdog(self.drift['Watchdog'])
        self.integral_error = 0.0  # ns·s (integral of ns over seconds)
        self.integral_cap = 0.001  # in ns
        self.prev_error_ns = 0.0
        self._last_pid_t = time.monotonic()
        self.prev_pix_val = 0.0
        print(f'{time.strftime("%x %X")} - Time Tool for {system} Started ... \n')

    def read_write(self):
        #if self.TT_Script_EN.get(timeout=1.0) != 1:
        #    return

        # Tunables inline (no defaults dict)
        self.Drift_Adjust_Threshold = _f(self.drift['Drift_Adjust_Threshold'].get(timeout=0.5), 0.0)
        self.Drift_Edge_Offset      = _f(self.drift['Drift_Edge_Offset'].get(timeout=0.5), 0.0)
        self.Drift_Num_Events       = _f(self.drift['Drift_Number_Events'].get(timeout=0.5), 1.0)
        num_events_i = max(1, int(round(self.Drift_Num_Events)))
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
        #print(f'{time.strftime("%x %X")} - Time Tool Script Enabled \n')

        while edge_count < num_events_i:
            ttall   = self.TTALL_PV.get(timeout=1.0)
            stage   = self.Stage_PV.get(timeout=1.0)
            ipm     = self.IPM_PV.get(timeout=1.0)
            shutter = self.Shutter_PV.get(timeout=1.0)

            pix, edge_pos, amp, amp2, bkg, fwhm = map(float, (ttall[0], ttall[1], ttall[2], ttall[3], ttall[4], ttall[5]))  # Unpack TTALL

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
            pix_ok     = pix != self.prev_pix_val and pix != 0
            ipm_ok     = (ipm_lo   < ipm      < ipm_hi)
            edge_ok    = (edge_lo  < edge_pos < edge_hi)
            amp_ok     = (amp_lo   < amp      < amp_hi)
            fwhm_ok    = (fwhm_lo  < fwhm     < fwhm_hi)
            stage_ok   = not bool(stage)     # stage must be zero to be OK (not moving)
            shutter_ok = not bool(shutter)   # shutter must be zero to be OK (shutter out)

            good = ipm_ok and edge_ok and amp_ok and pix_ok and fwhm_ok and stage_ok and shutter_ok

            if good:
                self.Time_Tool_Edges[edge_count] = edge_pos
                edge_count += 1
                self.prev_pix_val = pix
                last_good = time.monotonic()
                print(f'\033[FMeasurement {edge_count} of {num_events_i} - TT Edge Position {edge_pos:.3f} ps    ')

            if time.monotonic() - last_good > self.Wait:
                self.prev_pix_val = pix
                print(f"\033[F{time.strftime('%x %X')} - No Good Measurement Over {self.Wait} Seconds. "
                      f"Status -> IPM:{ipm_ok}, Edge:{edge_ok}, Amp:{amp_ok}, FWHM:{fwhm_ok}, Pix:{pix_ok}, Stage:{stage_ok}, Shutter:{shutter_ok} \n")
                break

            if time.monotonic() - wd_t > 0.5:
                self.W.check()
                wd_t += 0.5
            time.sleep(0.01)

        if edge_count == num_events_i:
            self._apply_drift_correction()

    def _apply_drift_correction(self):
        mean = float(np.mean(self.Time_Tool_Edges))
        mean_ps = mean - self.Drift_Edge_Offset
        std_dev_ps = float(np.std(self.Time_Tool_Edges))
        print(f'Mean of Edges = {mean:.6f}, Mean of Edges - Offset = {mean_ps:.6f} ps, Standard Deviation = {1000*std_dev_ps:.1f} fs \n')
        self.drift['Drift_Ave_Edge_Position'].put(mean, wait=True, timeout=1.0)                # write mean edge position (ps)
        self.drift['Drift_Std_Dev_Edge_Position'].put(std_dev_ps, wait=True, timeout=1.0)            # write std dev edge position (ps)
        # if self.TT_Drift_EN.get(timeout=1.0) != 1:
        if self.TT_Script_EN.get(timeout=1.0) != 1:
                return

        if abs(mean_ps) > self.Drift_Adjust_Threshold:
            old_ns = self.drift['Drift Correction Value'].get(timeout=1.0)
            p_gain = _f(self.drift['P Gain'].get(timeout=1.0), 0.0)
            i_gain = _f(self.drift['I Gain'].get(timeout=1.0), 0.0)
            d_gain = _f(self.drift['D Gain'].get(timeout=1.0), 0.0)

            # error in ns (convert ps -> ns), dt from last correction
            error_ns = mean_ps / 1000.0
            now = time.monotonic()
            dt = max(now - self._last_pid_t, 1e-6) # 1e-6 avoids div-by-zero; tiny dt

            # PID terms
            self.integral_error += error_ns * dt          # integrate error over time (ns·s)
            self.integral_error = np.clip(self.integral_error, -self.integral_cap, self.integral_cap)
            derivative = (error_ns - self.prev_error_ns) / dt

            delta = p_gain * error_ns + i_gain * self.integral_error + d_gain * derivative
            new_ns = old_ns - delta

            print(f'\033[FPID -> P:{p_gain:.4f}, I:{i_gain:.4f}, D:{d_gain:.4f}, Err(ns):{error_ns:.6f}, Integ:{self.integral_error:.6f}, Deriv:{derivative:.6f}, P*Err:{p_gain * error_ns:.8f}, I*Integ:{i_gain * self.integral_error:.8f}, D*Deriv:{d_gain * derivative:.8f}')
            print(f'{time.strftime('%x %X')} - Old Drift Correction = {old_ns:.6f} ns, New = {new_ns:.6f} ns, Delta = {delta:.6f} ns \n')

            self.drift['Drift Correction Value'].put(new_ns, wait=True, timeout=1.0)
            self.prev_error_ns = error_ns
            self._last_pid_t = now
        else:
            print(f'\033[F{time.strftime('%x %X')} - Mean of Edges - Offset ({abs(mean_ps):.4f}) < Adjustment Threshold ({self.Drift_Adjust_Threshold}). No Correction Applied. \n')
            self.integral_error = 0.0           # Reset integrator

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
