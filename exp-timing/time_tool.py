# time_tool.py (pyepics-only)
import time
import numpy as np
import watchdog3
from epics import PV, caget, caput
import sys as pysys
from typing import Dict, Tuple, List

SYSTEMS = {
    'FS11': dict(TTALL='XCS:TT:01:TTALL', DEV='LAS:FS11:VIT:', STAGE='XPP:LAS:MMN:16.MOVN', IPM='XPP:SB2:BMMON:SUM'),
    'FS14': dict(TTALL='CXI:TT:01:TTALL', DEV='LAS:FS14:VIT:', STAGE='CXI:LAS:MMN:09.MOVN', IPM='CXI:DG2:BMMON:SUM'),
    'XPP':  dict(TTALL='XCS:TT:01:TTALL', DEV='LAS:FS3:VIT:',  STAGE='XPP:LAS:MMN:16.MOVN', IPM='XPP:SB2:BMMON:SUM'),
    'XCS':  dict(TTALL='XCS:TT:01:TTALL', DEV='LAS:FS4:VIT:',  STAGE='XCS:LAS:MMN:01.MOVN', IPM='XCS:SB1:BMMON:SUM'),
    'MFX':  dict(TTALL='MFX:TT:01:TTALL', DEV='LAS:FS45:VIT:', STAGE='MFX:LAS:MMN:06.MOVN', IPM='MFX:DG2:BMMON:SUM'),
    'CXI':  dict(TTALL='CXI:TT:01:TTALL', DEV='LAS:FS5:VIT:',  STAGE='CXI:LAS:MMN:09.MOVN', IPM='CXI:DG2:BMMON:SUM'),
}

TTALL_FIELDS: List[Tuple[int, str]] = [(0, 'Pixel Pos'), (1, 'Edge Position'), (2, 'Amplitude'), (3, '2nd Amplitude'), (4, 'Background ref'), (5, 'FWHM')]

class time_tool():
    def __init__(self, system='FS14'):
        self.IPM_Threshold = 500.0
        self.Amplitude_Threshold = 0.02
        self.Drift_Adjustment_Threshold = 0.05
        self.FWHM_Threshold_Low = 30.0
        self.FWHM_Threshold_High = 250.0
        self.Number_Events = 61
        self.TimeTool_Edges = np.zeros(self.Number_Events, dtype=float)
        self.delay = 0.5

        cfg = SYSTEMS.get(system)
        print(f'Starting {system} ...')
        if not cfg:
            print(system + ' Not Found! Exiting')
            raise ValueError(f'Unknown system: {system}')

        TTALL_Name = cfg['TTALL']
        Dev_Base   = cfg['DEV']
        Stage_Name = cfg['STAGE']
        IPM_Name   = cfg['IPM']

        self.TTALL_PV = PV(TTALL_Name); self.TTALL_PV.wait_for_connection(timeout=1.0)
        self.Stage_PV = PV(Stage_Name); self.Stage_PV.wait_for_connection(timeout=1.0)
        self.IPM_PV   = PV(IPM_Name);   self.IPM_PV.wait_for_connection(timeout=1.0)
        self.TT_Script_EN = PV(Dev_Base + 'matlab:31'); self.TT_Script_EN.wait_for_connection(timeout=1.0)

        self.Name = [
            'Watchdog','Pixel Pos','Edge Position','Amplitude','2nd Amplitude','Background ref',
            'FWHM','Stage Moving?','IPM','Drift Correction Signal','Drift Correction Value',
            'IPM Good?','Amplitude Good?','FWHM Good?','Good TT Measurement?'
        ]
        bases = {
            'Watchdog': Dev_Base+'WATCHDOG',
            'Pixel Pos': Dev_Base+'PIX',
            'Edge Position': Dev_Base+'FS',
            'Amplitude': Dev_Base+'AMP',
            '2nd Amplitude': Dev_Base+'AMP_SEC',
            'Background ref': Dev_Base+'REF',
            'FWHM': Dev_Base+'FWHM',
            'Stage Moving?': Dev_Base+'STAGE',
            'IPM': Dev_Base+'IPM',
            'Drift Correction Signal': Dev_Base+'DRIFT_CORRECT_SIG',
            'Drift Correction Value': Dev_Base+'DRIFT_CORRECT_VAL',
            'IPM Good?': Dev_Base+'matlab:11',
            'Amplitude Good?': Dev_Base+'matlab:12',
            'FWHM Good?': Dev_Base+'matlab:13',
            'Good TT Measurement?': Dev_Base+'matlab:14',
        }

        # Store only the main PVs; no DESC/LOW/HIGH
        self.Drift_Correct: Dict[str, PV] = {}
        for name in self.Name:
            base = bases[name]
            pv = PV(base); pv.wait_for_connection(timeout=1.0)
            try:
                pv.get(timeout=1.0)  # optional warm cache
            except Exception:
                pass
            self.Drift_Correct[name] = pv

        # watchdog3 expects a PV-like object; pass PV directly
        self.W = watchdog3.watchdog(self.Drift_Correct['Watchdog'])

    def read_write(self):
        self.TT_Script_EN.get(timeout=1.0)
        run = (self.TT_Script_EN.value == 1)

        wd_val = self.Drift_Correct['Watchdog'].get(timeout=1.0)
        try:
            if int(wd_val) % 100 == 0:
                print(f'{time.strftime("%x %X")} - The Time Tool Script is {"Enabled" if run else "Disabled"}')
        except Exception:
            pass

        if not run:
            self.TT_Script_EN.put(0, wait=True, timeout=1.0)
            return

        edge_count = 0
        prev_pix_val = 0
        last_good = wd_times = time.monotonic()
        print(f'{time.strftime("%x %X")} - The Time Tool Script is Enabled')

        while edge_count < self.Number_Events:
            ttall = self.TTALL_PV.get(timeout=1.0)
            stage = self.Stage_PV.get(timeout=1.0)
            ipm   = self.IPM_PV.get(timeout=1.0)

            for idx, name in TTALL_FIELDS:
                self.Drift_Correct[name].put(float(ttall[idx]), wait=True, timeout=1.0)
            self.Drift_Correct['Stage Moving?'].put(float(stage), wait=True, timeout=1.0)
            self.Drift_Correct['IPM'].put(float(ipm), wait=True, timeout=1.0)

            ipm_val  = float(ipm)
            pix_val  = float(ttall[0])
            amp_val  = float(ttall[2])
            fwhm_val = float(ttall[5])
            stage_moving = bool(stage)  # 1 means moving, 0 means not

            stage_ok = not stage_moving
            ipm_ok  = ipm_val  > self.IPM_Threshold
            amp_ok  = amp_val  > self.Amplitude_Threshold
            pix_ok  = pix_val != prev_pix_val and pix_val != 0
            fwhm_ok = self.FWHM_Threshold_Low < fwhm_val < self.FWHM_Threshold_High

            self.Drift_Correct['IPM Good?'].put(int(ipm_ok), wait=True, timeout=1.0)
            self.Drift_Correct['Amplitude Good?'].put(int(amp_ok), wait=True, timeout=1.0)
            self.Drift_Correct['FWHM Good?'].put(int(fwhm_ok), wait=True, timeout=1.0)
            good = pix_ok and ipm_ok and amp_ok and fwhm_ok and stage_ok
            self.Drift_Correct['Good TT Measurement?'].put(int(good), wait=True, timeout=1.0)

            if good:
                edge = float(ttall[1])
                prev_pix_val = float(ttall[0])
                print(f'Good Measurement! - TT Edge position {edge:.3f} ps')
                self.TimeTool_Edges[edge_count] = edge
                edge_count += 1
                last_good = time.monotonic()

            if time.monotonic() - last_good > 60:
                print(f"No good measurement over one minute. Status -> IPM:{ipm_ok}, Amp:{amp_ok}, FWHM:{fwhm_ok}, Pix:{pix_ok}, Stage:{stage_ok}")
                break
                
            if time.monotonic() - wd_times > 0.5:
                self.W.check()
                wd_times += 0.5
            time.sleep(0.01)

        # print(f'Edge count = {edge_count}')
        if edge_count == self.Number_Events:
            edge_mean = float(np.mean(self.TimeTool_Edges))# - 0.5 # Middle of the time tool is 0.5?
            # print(f'Edges Array: [{" ".join(f"{e:.3f}" for e in self.TimeTool_Edges)}]')
            print(f'{"Good" if ipm_ok else "Low"} Signal in IPM: {ipm_val:.3f}')
            print(f'{"Good" if amp_ok else "Low"} Amplitude in TT: {amp_val:.3f}')
            print(f'{"Good" if fwhm_ok else "Bad"} FWHM in TT: {fwhm_val:.3f}')
            print(f'Mean of Edges = {edge_mean:.6f} ps')

            if abs(edge_mean) > self.Drift_Adjustment_Threshold:
                old_val = float(self.Drift_Correct['Drift Correction Value'].get(timeout=1.0))
                p_gain  = float(self.Drift_Correct['Drift Correction Signal'].get(timeout=1.0))
                edge_mean = edge_mean / 1000  # ps -> ns
                new_val = p_gain * edge_mean + old_val
                print(f'Old Drift Correction value = {old_val:.6f} ns')
                print(f'New Drift Correction value = {new_val:.6f} ns')
                # new_val = new_val / 1000  # ps -> ns
                self.Drift_Correct['Drift Correction Value'].put(new_val, wait=True, timeout=1.0)
                time.sleep(1)

def run():
    system = pysys.argv[1] if len(pysys.argv) > 1 else 'FS14'
    T = time_tool(system)
    print('Enter main loop')
    while T.W.error == 0:
        T.W.check()
        time.sleep(T.delay)
        try:
            T.read_write()
        except Exception as e:
            print(f'Crashed: {e}, restarting')
            T = time_tool(system)
            if T.W.error:
                return

if __name__ == "__main__":
    run()
