import time
from psp.Pv import Pv

class drift_correction():
    """Takes the ATM error PV, filters by edge amplitude, and applies an offset via the laser lockers HLA."""
    def __init__(self):
        # create PV objects
        #self.atm_err_pv = Pv('RIX:TIMETOOL:TTALL')  # timetool waveform PV from the DAQ - COMMENT IF TESTING
        self.atm_err_ampl_pv = Pv('LAS:UNDS:FLOAT:59')  # PV to hold dummy edge amplitude for testing - COMMENT IF NOT TESTING
        self.atm_err_flt_pos_fs_pv = Pv('LAS:UNDS:FLOAT:58')  # PV to hold dummy fs error for testing - COMMENT IF NOT TESTING
        self.atm_fb_pv = Pv('LAS:UNDS:FLOAT:68')  # hook for ATM feedback in laser locker HLA - CURRENTLY DUMMY PV FOR TESTING
        self.ampl_pv = Pv('LAS:UNDS:FLOAT:60')  # edge amplitude
        self.flt_pos_fs_pv = Pv('LAS:UNDS:FLOAT:62')  # position in fs
        self.flt_pos_offset_pv = Pv('LAS:UNDS:FLOAT:57')  # offset in (fs ?) - based on real ATM data
        self.ampl_min_pv = Pv('LAS:UNDS:FLOAT:63')  # minimum allowable edge amplitude for correction
        self.ampl_max_pv = Pv('LAS:UNDS:FLOAT:64')  # maximum allowable edge amplitude for correction
        self.fb_gain_pv = Pv('LAS:UNDS:FLOAT:65')  # gain of feedback loop
        self.sample_size_pv = Pv('LAS:UNDS:FLOAT:66')  # number of edges to average over
        self.on_off_pv = Pv('LAS:UNDS:FLOAT:67')  # PV to turn drift correction on/off
        # connect to PVs
        #self.atm_err_pv.connect(timeout=1.0)  # COMMENT THIS LINE IF TESTING
        self.atm_err_ampl_pv.connect(timeout=1.0)  # COMMENT THIS LINE IF NOT TESTING
        self.atm_err_flt_pos_fs_pv.connect(timeout=1.0)  # COMMENT THIS LINE IF NOT TESTING
        self.atm_fb_pv.connect(timeout=1.0)
        self.ampl_pv.connect(timeout=1.0)
        self.flt_pos_fs_pv.connect(timeout=1.0)
        self.flt_pos_offset_pv.connect(timeout=1.0)
        self.ampl_min_pv.connect(timeout=1.0)
        self.ampl_max_pv.connect(timeout=1.0)
        self.fb_gain_pv.connect(timeout=1.0)
        self.sample_size_pv.connect(timeout=1.0)
        self.on_off_pv.connect(timeout=1.0)


    def correct(self):
        """Takes ATM waveform PV data, applies filtering to detemine valid error values, and applies a correction to laser locker HLA."""
        self.ampl_vals = dict()  # dictionary to hold amplitude values for averaging
        self.error_vals = dict()  # dictionary to hold error values for averaging
        #self.atm_err = self.atm_err_pv.get(timeout=1.0)  # COMMENT THIS LINE IF TESTING
        #self.flt_pos_fs = self.atm_err[4]  # COMMENT THIS LINE IF TESTING
        self.flt_pos_fs = self.atm_err_flt_pos_fs_pv.get(timeout = 1.0)  # initial error - COMMENT THIS LINE IF NOT TESTING
        self.count = 0  # counter to track number of error values in dict
        self.flt_pos_offset = self.flt_pos_offset_pv.get(timeout=1.0)
        self.sample_size = self.sample_size_pv.get(timeout=1.0)  # get user-set sample size
        # loop for adding error values to dictionary if it meets threshold conditions
        while (self.count < self.sample_size):
            # get current PV values
            #self.atm_err = self.atm_err_pv.get(timeout=1.0)  # COMMENT THIS LINE IF TESTING
            self.atm_err0 = self.atm_err_ampl_pv.get(timeout = 1.0)  # COMMENT THIS LINE IF NOT TESTING
            self.atm_err4 = self.atm_err_flt_pos_fs_pv.get(timeout = 1.0)  # COMMENT THIS LINE IF NOT TESTING
            self.ampl_min = self.ampl_min_pv.get(timeout=1.0)
            self.ampl_max = self.ampl_max_pv.get(timeout=1.0)
            # apply filtering, confirm fresh values, and add to dictionary
            #if (self.atm_err[0] > self.ampl_min) and (self.atm_err[0] < self.ampl_max) and (self.atm_err[4] > 3000) and (self.atm_err[4] < 4250) and (self.flt_pos_fs != self.atm_err[4]):  # COMMENT THIS LINE IF TESTING
            if (self.atm_err0 > self.ampl_min) and (self.atm_err0 < self.ampl_max) and (self.atm_err4 > 3000) and (self.atm_err4 < 4250) and (self.atm_err4 != self.flt_pos_fs):  # COMMENT THIS LINE IF NOT TESTING
                #self.ampl = self.atm_err[0]  # unpack filter parameter - COMMENT THIS LINE IF TESTING
                #self.flt_pos_fs = self.atm_err[4] - self.flt_pos_offset  # COMMENT THIS LINE IF TESTING
                self.ampl = self.atm_err0  # COMMENT THIS LINE IF NOT TESTING
                self.flt_pos_fs = self.atm_err4 - self.flt_pos_offset  # COMMENT THIS LINE IF NOT TESTING
                self.ampl_vals[self.count] = self.ampl
                self.error_vals[self.count] = self.flt_pos_fs
                self.count += 1
        # averaging
        self.avg_ampl = sum(self.ampl_vals.values()) / len(self.ampl_vals)
        self.avg_error = sum(self.error_vals.values()) / len(self.error_vals)
        # write filter parameter and error value to PVs for easier monitoring
        self.ampl_pv.put(value=self.avg_ampl, timeout=1.0)
        self.flt_pos_fs_pv.put(value=self.avg_error, timeout=1.0)
        # apply correction
        self.fb_gain = self.fb_gain_pv.get(timeout=1.0)  # pull gain PV value
        self.on_off = self.on_off_pv.get(timeout=1.0)
        self.correction = (self.avg_error / 1000000) * self.fb_gain  # scale from fs to ns and apply gain
        if (self.on_off == 1) and ((abs(self.correction) < 0.003)):  # check if drift correction has been turned on and limit corrections to 3 ps
            self.atm_fb_pv.put(value=self.correction, timeout=1.0)  # write to correction PV
        else:
            self.atm_fb_pv.put(value=0, timeout=1.0)  # if drift correction is turned off, zero out correction value


def run():
    correction = drift_correction()  # initialize
    try:
        while True:
            correction.correct()  # pull data and filter, then apply correction
            time.sleep(1.0)  # keep loop from spinning too fast
    except KeyboardInterrupt:
        print("Script terminated by user.")


if __name__ == "__main__":
    run()
            

