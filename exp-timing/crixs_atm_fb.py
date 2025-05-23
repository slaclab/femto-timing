import time
from psp.Pv import Pv

class drift_correction():
    """Takes the ATM error PV, filters by edge amplitude, and applies an offset via the laser lockers HLA."""
    def __init__(self):
        # create PV objects
        self.atm_err_pv = Pv('RIX:TIMETOOL:TTALL')  # timetool waveform PV from the DAQ
        self.atm_fb_pv = Pv('LAS:UNDS:FLOAT:68')  # hook for ATM feedback in laser locker HLA - CURRENTLY DUMMY PV FOR TESTING
        self.ampl_pv = Pv('LAS:UNDS:FLOAT:60')  # edge amplitude
        self.flt_pos_ps_pv = Pv('LAS:UNDS:FLOAT:62')  # position in ps
        self.ampl_min_pv = Pv('LAS:UNDS:FLOAT:63')  # minimum allowable edge amplitude for correction
        self.ampl_max_pv = Pv('LAS:UNDS:FLOAT:64')  # maximum allowable edge amplitude for correction
        self.fb_gain_pv = Pv('LAS:UNDS:FLOAT:65')  # gain of feedback loop
        self.sample_size_pv = Pv('LAS:UNDS:FLOAT:66')  # number of edges to average over
        self_on_off_pv = Pv('LAS:UNDS:FLOAT:67')  # PV to turn drift correction on/off
        # connect to PVs
        self.atm_err_pv.connect(timeout = 1.0) 
        self.atm_fb_pv.connect(timeout = 1.0)
        self.ampl_pv.connect(timeout = 1.0)
        self.flt_pos_ps_pv.connect(timeout = 1.0)
        self.ampl_min_pv.connect(timeout = 1.0)
        self.ampl_max_pv.connect(timeout = 1.0)
        self.fb_gain_pv.connect(timeout = 1.0)
        self.sample_size_pv.connect(timeout = 1.0)
        self_on_off_pv.connect(timeout = 1.0)

    def correct(self):
        """Takes ATM waveform PV data, applies filtering to detemine valid error values, and applies a correction to laser locker HLA."""
        self.ampl_vals = dict()  # dictionary to hold amplitude values for averaging
        self.error_vals = dict()  # dictionary to hold error values for averaging
        self.count = 0  # counter to track number of error values in dict
        self.sample_size = self.sample_size_pv.get(timeout = 1.0)  # get user-set sample size
        # loop for adding error values to dictionary if it meets threshold conditions
        while (self.count < self.sample_size):
            # get current PV values
            self.atm_err = self.atm_err_pv.get(timeout = 1.0)
            self.ampl_min = self.ampl_min_pv.get(timeout = 1.0)
            self.ampl_max = self.ampl_max_pv.get(timeout = 1.0)
            # apply filtering, confirm fresh values, and add to dictionary
            if (self.atm_err[0] > self.ampl_min) and (self.atm_err[0] < self.ampl_max) and (self.flt_pos_ps != self.atm_err[4]):
                self.ampl = self.atm_err[0]  # unpack filter parameter
                self.flt_pos_ps = self.atm_err[4]
                self.ampl_vals[self.count] = self.ampl
                self.error_vals[self.count] = self.flt_pos_ps
                self.count+=1
        # averaging
        self.avg_ampl = sum(self.ampl_vals.values()) / len(self.ampl_vals)
        self.avg_error = sum(self.error_vals.values()) / len(self.error_vals)
        # write filter parameter and error value to PVs for easier monitoring
        self.ampl_pv.put(value = self.avg_ampl, timeout = 1.0)
        self.flt_pos_ps_pv.put(value = self.avg_error, timeout = 1.0)
        # apply correction
        self.fb_gain = self.fb_gain_pv.get(timeout = 1.0)  # pull gain PV value
        self.on_off = self.on_off_pv.get(timeout = 1.0)
        if (self.on_off == 1):  # check if drift correction has been turned on
            self.atm_fb_pv.put(value = (self.avg_error/1000) * self.fb_gain, timeout = 1.0)  # scale from ps to ns, apply gain, and write to correction PV
        

def run():
    correction = drift_correction() # initialize
    while True:
        try:
            correction.correct() # pull data and filter, then apply correction
        except KeyboardInterrupt:
            print("Script terminated by user.")
        time.sleep(1.0)  # keep loop from spinning too fast


if __name__ == "__main__":
    run()
            

