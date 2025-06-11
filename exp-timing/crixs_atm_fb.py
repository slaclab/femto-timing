import time
from psp.Pv import Pv

class drift_correction():
    """Takes the ATM error PV, filters by edge amplitude, and applies an offset via the laser lockers HLA."""
    def __init__(self):
        # create PV objects
        #self.atm_err_pv = Pv('RIX:TIMETOOL:TTALL')  # timetool waveform PV from the DAQ - COMMENT IF TESTING
        self.atm_err_ampl_pv = Pv('LAS:UNDS:FLOAT:59')  # PV to hold dummy edge amplitude for testing - COMMENT IF NOT TESTING
        self.atm_err_flt_pos_fs_pv = Pv('LAS:UNDS:FLOAT:58')  # PV to hold dummy fs error for testing - COMMENT IF NOT TESTING
        self.atm_fb_pv = Pv('LAS:LHN:LLG2:02:PHASCTL:ATM_FBK_OFFSET')  # hook for ATM feedback in laser locker HLA
        self.ampl_min_pv = Pv('LAS:UNDS:FLOAT:63')  # minimum allowable edge amplitude for correction
        self.ampl_max_pv = Pv('LAS:UNDS:FLOAT:64')  # maximum allowable edge amplitude for correction
        self.curr_ampl_pv = Pv('LAS:UNDS:FLOAT:55')  # edge amplitude for the current shot
        self.ampl_pv = Pv('LAS:UNDS:FLOAT:60')  # average edge amplitude over sample period
        self.fwhm_min_pv = Pv('LAS:UNDS:FLOAT:49')  # minimum allowable edge FWHM for correction
        self.fwhm_max_pv = Pv('LAS:UNDS:FLOAT:48')  # maximum allowable edge FWHM for correction
        self.curr_fwhm_pv = Pv('LAS:UNDS:FLOAT:47')  # edge FWHM for the current shot
        self.fwhm_pv = Pv('LAS:UNDS:FLOAT:46')  # average edge FWHM over sample period
        self.pos_fs_min_pv = Pv('LAS:UNDS:FLOAT:53')  # minimum allowable edge position in fs
        self.pos_fs_max_pv = Pv('LAS:UNDS:FLOAT:52')  # maximum allowable edge position in fs
        self.curr_flt_pos_fs_pv = Pv('LAS:UNDS:FLOAT:54')  # position in fs of current edge
        self.flt_pos_fs_pv = Pv('LAS:UNDS:FLOAT:62')  # average position in fs over sample period
        self.flt_pos_offset_pv = Pv('LAS:UNDS:FLOAT:57')  # offset in (fs ?) - based on real ATM data
        self.txt_pv = Pv('LM2K2:MCS2:03:m10.RBV')  # TXT stage position PV for filtering
        self.fb_gain_pv = Pv('LAS:UNDS:FLOAT:65')  # gain of feedback loop
        self.sample_size_pv = Pv('LAS:UNDS:FLOAT:66')  # number of edges to average over
        self.on_off_pv = Pv('LAS:UNDS:FLOAT:67')  # PV to turn drift correction on/off
        self.debug_mode_pv = Pv('LAS:UNDS:FLOAT:56')  # PV to turn debug mode on/off
        # connect to PVs
        #self.atm_err_pv.connect(timeout=1.0)  # COMMENT THIS LINE IF TESTING
        self.atm_err_ampl_pv.connect(timeout=1.0)  # COMMENT THIS LINE IF NOT TESTING
        self.atm_err_flt_pos_fs_pv.connect(timeout=1.0)  # COMMENT THIS LINE IF NOT TESTING
        self.atm_fb_pv.connect(timeout=1.0)
        self.ampl_min_pv.connect(timeout=1.0)
        self.ampl_max_pv.connect(timeout=1.0)
        self.curr_ampl_pv.connect(timeout=1.0)
        self.ampl_pv.connect(timeout=1.0)
        self.fwhm_min_pv.connect(timeout=1.0)
        self.fwhm_max_pv.connect(timeout=1.0)
        self.curr_fwhm_pv.connect(timeout=1.0)
        self.fwhm_pv.connect(timeout=1.0)
        self.pos_fs_min_pv.connect(timeout=1.0)
        self.pos_fs_max_pv.connect(timeout=1.0)
        self.curr_flt_pos_fs_pv.connect(timeout=1.0)
        self.flt_pos_fs_pv.connect(timeout=1.0)
        self.txt_pv.connect(timeout=1.0)
        self.flt_pos_offset_pv.connect(timeout=1.0)
        self.fb_gain_pv.connect(timeout=1.0)
        self.sample_size_pv.connect(timeout=1.0)
        self.on_off_pv.connect(timeout=1.0)
        self.debug_mode_pv.connect(timeout=1.0)


    def correct(self):
        """Takes ATM waveform PV data, applies filtering to detemine valid error values, and applies a correction to laser locker HLA."""
        self.ampl_vals = dict()  # dictionary to hold amplitude values for averaging
        self.fwhm_vals = dict()  # dictionary to hold fwhm values for averaging
        self.error_vals = dict()  # dictionary to hold error values for averaging
        #self.atm_err = self.atm_err_pv.get(timeout=60.0)  # COMMENT THIS LINE IF TESTING
        self.flt_pos_offset = self.flt_pos_offset_pv.get(timeout=1.0)  # pull current offset
        #self.flt_pos_fs = (self.atm_err[2] * 1000) - self.flt_pos_offset  # COMMENT THIS LINE IF TESTING
        self.flt_pos_fs = self.atm_err_flt_pos_fs_pv.get(timeout = 1.0)  # initial error - COMMENT THIS LINE IF NOT TESTING
        self.ampl_min = self.ampl_min_pv.get(timeout=1.0)
        self.ampl_max = self.ampl_max_pv.get(timeout=1.0)
        self.fwhm_min = self.fwhm_min_pv.get(timeout=1.0)
        self.fwhm_max = self.fwhm_max_pv.get(timeout=1.0)
        self.pos_fs_min = self.pos_fs_min_pv.get(timeout=1.0)
        self.pos_fs_max = self.pos_fs_max_pv.get(timeout=1.0)
        self.txt_prev = round(self.txt_pv.get(timeout=1.0), 1)
        self.flt_pos_offset = self.flt_pos_offset_pv.get(timeout=1.0)  # pull current offset
        self.good_count = 0  # counter to track number of error values in dict
        self.bad_count = 0  # counter to track how many times filter thresholds have not been met
        self.sample_size = self.sample_size_pv.get(timeout=1.0)  # get user-set sample size
        # loop for adding error values to dictionary if it meets threshold conditions
        while (self.good_count < self.sample_size):
            # get current PV values
            #self.atm_err = self.atm_err_pv.get(timeout=60.0)  # COMMENT THIS LINE IF TESTING
            self.atm_err0 = self.atm_err_ampl_pv.get(timeout = 1.0)  # COMMENT THIS LINE IF NOT TESTING
            self.atm_err2 = self.atm_err_flt_pos_fs_pv.get(timeout = 1.0) - self.flt_pos_offset  # COMMENT THIS LINE IF NOT TESTING
            #self.curr_flt_pos_fs = (self.atm_err[2] * 1000) - self.flt_pos_offset  # calcuated current offset adjusted edge position in fs - COMMENT THIS LINE IF TESTING
            # every ten shots, check if filtering thresholds have been updated
            if (self.bad_count > 9):
                # pull current filtering thresholds
                self.ampl_min = self.ampl_min_pv.get(timeout=1.0)
                self.ampl_max = self.ampl_max_pv.get(timeout=1.0)
                self.fwhm_min = self.fwhm_min_pv.get(timeout=1.0)
                self.fwhm_max = self.fwhm_max_pv.get(timeout=1.0)
                self.pos_fs_min = self.pos_fs_min_pv.get(timeout=1.0)
                self.pos_fs_max = self.pos_fs_max_pv.get(timeout=1.0)
                self.flt_pos_offset = self.flt_pos_offset_pv.get(timeout=1.0)  # pull current offset
                self.bad_count = 0
            # update tracking PVs
            self.curr_ampl_pv.put(value=self.atm_err0, timeout=1.0)  # COMMENT THIS LINE IF NOT TESTING
            self.curr_flt_pos_fs_pv.put(value=self.atm_err2, timeout=1.0)
            #self.curr_ampl_pv.put(value=self.atm_err[0], timeout=1.0)  # COMMENT THIS LINE IF TESTING
            #self.curr_fwhm_pv.put(value=self.atm_err[3], timeout=1.0)  # COMMENT THIS LINE IF TESTING
            #self.curr_flt_pos_fs_pv.put(value=self.curr_flt_pos_fs, timeout=1.0)  # COMMENT THIS LINE IF TESTING
            # apply filtering, confirm fresh values, and add to dictionary
            #if (self.atm_err[0] > self.ampl_min) and (self.atm_err[0] < self.ampl_max) and (self.atm_err[3] > self.fwhm_min) and (self.atm_err[3] < self.fwhm_max) and (self.curr_flt_pos_fs > self.pos_fs_min) and (self.curr_flt_pos_fs < self.pos_fs_max) and (self.flt_pos_fs != self.curr_flt_pos_fs) and (round(self.txt_pv.get(timeout=1.0), 1) == self.txt_prev):  # COMMENT THIS LINE IF TESTING
            if (self.atm_err0 > self.ampl_min) and (self.atm_err0 < self.ampl_max) and (self.atm_err2 > self.pos_fs_min) and (self.atm_err2 < self.pos_fs_max) and (self.atm_err2 != self.flt_pos_fs):  # COMMENT THIS LINE IF NOT TESTING
                #self.ampl = self.atm_err[0]  # unpack ampl filter parameter - COMMENT THIS LINE IF TESTING
                #self.fwhm = self.atm_err[3]  # unpack fwhm filter parametet - COMMENT THIS LINE IF TESTING
                #self.flt_pos_fs = self.curr_flt_pos_fs  # COMMENT THIS LINE IF TESTING
                print('Entered corr loop')
                self.ampl = self.atm_err0  # COMMENT THIS LINE IF NOT TESTING
                self.flt_pos_fs = self.atm_err2 - self.flt_pos_offset  # COMMENT THIS LINE IF NOT TESTING
                # add valid amplitudes and edges to dictionary
                self.ampl_vals[self.good_count] = self.ampl
                #self.fwhm_vals[self.good_count] = self.fwhm  # COMMENT THIS LINE IF TESTING
                self.error_vals[self.good_count] = self.flt_pos_fs
                self.good_count += 1
                self.bad_count = 0
            else:
                self.bad_count += 1
            self.txt_prev = round(self.txt_pv.get(timeout=1.0), 1)  # update previous txt position for filtering
        # averaging
        self.avg_ampl = sum(self.ampl_vals.values()) / len(self.ampl_vals)
        #self.avg_fwhm = sum(self.fwhm_vals.values()) / len(self.fwhm_vals)  # COMMENT THIS LINE IF TESTING
        self.avg_error = sum(self.error_vals.values()) / len(self.error_vals)
        # write average filter parameter and error value to PVs for easier monitoring
        self.ampl_pv.put(value=self.avg_ampl, timeout=1.0)
        #self.fwhm_pv.put(value=self.avg_fwhm, timeout=1.0)  # COMMENT THIS LINE IF TESTING
        self.flt_pos_fs_pv.put(value=self.avg_error, timeout=1.0)
        # apply correction
        self.fb_gain = self.fb_gain_pv.get(timeout=1.0)  # pull gain PV value
        self.on_off = self.on_off_pv.get(timeout=1.0)
        self.correction = (self.avg_error / 1000000) * self.fb_gain  # scale from fs to ns and apply gain
        if (self.on_off == 1) and ((abs(self.correction) < 0.0015)):  # check if drift correction has been turned on and limit corrections to 1.5 ps
            self.atm_fb_pv.put(value=self.correction, timeout=1.0)  # write to correction PV
        elif ((self.on_off == 1) and ((abs(self.correction) >= 0.0015))):
            pass
        else:
            self.atm_fb_pv.put(value=0, timeout=1.0)  # if drift correction is turned off, zero out correction value
        # additional print statement for rapid debugging
        self.debug_mode = self.debug_mode_pv.get(timeout=1.0)
        if (self.debug_mode == 1):  # keep debug mode turned off when using tester script
            print('Most recent correction value in fs: ', self.correction * 1000000)


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
            

