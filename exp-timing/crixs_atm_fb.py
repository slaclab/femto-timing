import time
from collections import deque
import numpy as np
from psp.Pv import Pv

class drift_correction():
    """Takes the ATM error PV, filters by edge amplitude, and applies an offset via the laser lockers HLA."""
    def __init__(self):
        # create PV objects
        self.atm_err_pv = Pv('RIX:TIMETOOL:TTALL')  # timetool waveform PV from the DAQ - COMMENT IF TESTING
        #self.atm_err_ampl_pv = Pv('LAS:UNDS:FLOAT:59')  # PV to hold dummy edge amplitude for testing - COMMENT IF NOT TESTING
        #self.atm_err_flt_pos_fs_pv = Pv('LAS:UNDS:FLOAT:58')  # PV to hold dummy fs error for testing - COMMENT IF NOT TESTING
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
        self.flt_pos_offset_pv = Pv('LAS:UNDS:FLOAT:57')  # offset in fs - based on real ATM data
        self.txt_pv = Pv('LM2K2:MCS2:03:m10.RBV')  # TXT stage position PV for filtering
        self.heartbeat_pv = Pv('LAS:UNDS:FLOAT:41')  # heartbeat to show script is running
        self.filter_state_pv = Pv('LAS:UNDS:FLOAT:42')  # indicates which filtering conditions are not met 
        self.avg_mode_pv = Pv('LAS:UNDS:FLOAT:44')  # PV so user can select desired averaging mode
        self.decay_factor_pv = Pv('LAS:UNDS:FLOAT:43')  # decay factor for decaying median filter
        self.fb_direction_pv = Pv('LAS:UNDS:FLOAT:45')  # direction of the feedback correction
        self.fb_gain_pv = Pv('LAS:UNDS:FLOAT:65')  # gain of feedback loop
        self.sample_size_pv = Pv('LAS:UNDS:FLOAT:66')  # number of edges to average over
        self.on_off_pv = Pv('LAS:UNDS:FLOAT:67')  # PV to turn drift correction on/off
        self.debug_mode_pv = Pv('LAS:UNDS:FLOAT:56')  # PV to turn debug mode on/off
        # parameter and container initialization
        self.ampl_vals = deque()  # dictionary to hold amplitude values for averaging
        self.fwhm_vals = deque()  # dictionary to hold fwhm values for averaging
        self.error_vals = deque()  # dictionary to hold error values for averaging
        self.heartbeat_counter = 0 # init counter to update heartbeat PV

    
    def correct(self):
        """Takes ATM waveform PV data, applies filtering to detemine valid error values, and applies a correction to laser locker HLA."""
        self.atm_err = self.atm_err_pv.get(timeout=60.0)  # COMMENT THIS LINE IF TESTING
        self.atm_fb = self.atm_fb_pv.get(timeout=60.0)  # get current ATM FB offset
        self.flt_pos_offset = self.flt_pos_offset_pv.get(timeout=1.0)  # pull current offset
        self.flt_pos_fs = (self.atm_err[2] * 1000) - self.flt_pos_offset  # COMMENT THIS LINE IF TESTING
        #self.flt_pos_fs = self.atm_err_flt_pos_fs_pv.get(timeout = 1.0)  # initial error - COMMENT THIS LINE IF NOT TESTING
        self.ampl_min = self.ampl_min_pv.get(timeout=1.0)
        self.ampl_max = self.ampl_max_pv.get(timeout=1.0)
        self.fwhm_min = self.fwhm_min_pv.get(timeout=1.0)
        self.fwhm_max = self.fwhm_max_pv.get(timeout=1.0)
        self.pos_fs_min = self.pos_fs_min_pv.get(timeout=1.0)
        self.pos_fs_max = self.pos_fs_max_pv.get(timeout=1.0)
        self.txt_prev = round(self.txt_pv.get(timeout=1.0), 1)
        self.bad_count = 0  # counter to track how many times filter thresholds have not been met
        self.sample_size = self.sample_size_pv.get(timeout=1.0)  # get user-set sample size
        # ============== loop for filling buffer ======================
        while (len(self.error_vals) < self.sample_size):
            # get current PV values
            self.atm_err = self.atm_err_pv.get(timeout=60.0)  # COMMENT THIS LINE IF TESTING
            #self.atm_err0 = self.atm_err_ampl_pv.get(timeout = 1.0)  # COMMENT THIS LINE IF NOT TESTING
            #self.atm_err2 = self.atm_err_flt_pos_fs_pv.get(timeout = 1.0) + self.flt_pos_offset  # COMMENT THIS LINE IF NOT TESTING
            self.curr_flt_pos_fs = (self.atm_err[2] * 1000) - self.flt_pos_offset  # calcuated current offset adjusted edge position in fs - COMMENT THIS LINE IF TESTING
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
            #self.curr_ampl_pv.put(value=self.atm_err0, timeout=1.0)  # COMMENT THIS LINE IF NOT TESTING
            #self.curr_flt_pos_fs_pv.put(value=self.atm_err2, timeout=1.0) # COMMENT THIS LINE IF NOT TESTING
            self.curr_ampl_pv.put(value=self.atm_err[0], timeout=1.0)  # COMMENT THIS LINE IF TESTING
            self.curr_fwhm_pv.put(value=self.atm_err[3], timeout=1.0)  # COMMENT THIS LINE IF TESTING
            self.curr_flt_pos_fs_pv.put(value=self.curr_flt_pos_fs, timeout=1.0)  # COMMENT THIS LINE IF TESTING
            # ============= filtering ==============
            self.filter_state = 0  # 0: passes all filter conditions
            if not (self.atm_err[0] > self.ampl_min): self.filter_state = 1  # edge amplitude too low
            if not (self.atm_err[0] < self.ampl_max): self.filter_state = 2  # edge amplitude too high
            if not (self.atm_err[3] > self.fwhm_min): self.filter_state = 3  # edge FWHM too low
            if not (self.atm_err[3] < self.fwhm_max): self.filter_state = 4  # edge FWHM too
            if not (self.curr_flt_pos_fs > self.pos_fs_min): self.filter_state = 5  # edge position too low
            if not (self.curr_flt_pos_fs < self.pos_fs_max): self.filter_state = 6  # edge position too high
            if not (self.flt_pos_fs != self.curr_flt_pos_fs): self.filter_state = 7  # edge position the same as last time
            if not (round(self.txt_pv.get(timeout=1.0), 1) == self.txt_prev): self.filter_state = 8  # txt stage is moving
            self.filter_state_pv.put(value=self.filter_state, timeout=1.0)  # update filter state monitoring PV
            if (self.filter_state == 0):  # COMMENT THIS LINE IF TESTING
            #if (self.atm_err0 > self.ampl_min) and (self.atm_err0 < self.ampl_max) and (self.atm_err2 > self.pos_fs_min) and (self.atm_err2 < self.pos_fs_max) and (self.atm_err2 != self.flt_pos_fs):  # COMMENT THIS LINE IF NOT TESTING
                self.ampl = self.atm_err[0]  # unpack ampl filter parameter - COMMENT THIS LINE IF TESTING
                self.fwhm = self.atm_err[3]  # unpack fwhm filter parametet - COMMENT THIS LINE IF TESTING
                self.flt_pos_fs = self.curr_flt_pos_fs  # COMMENT THIS LINE IF TESTING
                #self.ampl = self.atm_err0  # COMMENT THIS LINE IF NOT TESTING
                #self.flt_pos_fs = self.atm_err2  # COMMENT THIS LINE IF NOT TESTING
                # add valid amplitudes and edges to dictionary
                self.ampl_vals.append(self.ampl)
                self.fwhm_vals.append(self.fwhm)  # COMMENT THIS LINE IF TESTING
                self.error_vals.append(self.flt_pos_fs)
                self.bad_count = 0
            else:
                self.bad_count += 1
            self.txt_prev = round(self.txt_pv.get(timeout=1.0), 1)  # update previous txt position for filtering
        # ============= averaging ===============
        self.avg_mode = self.avg_mode_pv.get(timeout=1.0)
        if (self.avg_mode == 1):  # block averaging
            self.avg_ampl = sum(self.ampl_vals.values()) / len(self.ampl_vals)
            self.avg_fwhm = sum(self.fwhm_vals.values()) / len(self.fwhm_vals)  # COMMENT THIS LINE IF TESTING
            self.avg_error = sum(self.error_vals.values()) / len(self.error_vals)
            # reset deques completely for next iteration
            self.ampl_vals.clear()
            self.fwhm_vals.clear()
            self.error_vals.clear()
        elif (self.avg_mode == 2):  # moving average
            self.avg_ampl = sum(self.ampl_vals.values()) / len(self.ampl_vals)
            self.avg_fwhm = sum(self.fwhm_vals.values()) / len(self.fwhm_vals)  # COMMENT THIS LINE IF TESTING
            self.avg_error = sum(self.error_vals.values()) / len(self.error_vals)
            # remove oldest element from deques
            self.ampl_vals.popleft()
            self.fwhm_vals.popleft()
            self.error_vals.popleft()
        else:  # decaying median filter
            # first, calculate moving average for amplitude and FWHM
            self.avg_ampl = sum(self.ampl_vals.values()) / len(self.ampl_vals)
            self.avg_fwhm = sum(self.fwhm_vals.values()) / len(self.fwhm_vals)  # COMMENT THIS LINE IF TESTING
            # then calculate decaying median edge position
            self.decay_factor = self.decay_factor_pv.get(timeout=1.0)
            self.weights = [self.decay_factor ** (self.sample_size - i - 1) for i in range(self.sample_size)]  # calculate weight of each element in deque
            self.weighted_values = [(self.error_vals[i], self.weights[i]) for i in range(self.sample_size)]  # elements are paired with weights
            self.sorted_values = sorted(self.weighted_values, key=lambda x: x[0])  # sort element/weight pairs by element value
            self.cumulative_weights = np.cumsum([val[1] for val in self.sorted_values])  # calculate the cumulative weight
            self.total_weight = self.cumulative_weights[-1]
            self.target_weight = self.total_weight / 2
            for value, cum_weight in zip([val[0] for val in self.sorted_values], self.cumulative_weights):  # loop through element/weight pairs until target weight reached
                if cum_weight >= self.target_weight:
                    self.avg_error = value
            # remove oldest element from deques
            self.ampl_vals.popleft()
            self.fwhm_vals.popleft()
            self.error_vals.popleft()
        # ======= updates PVs & apply correction =================
        # write average filter parameter and error value to PVs for easier monitoring
        self.ampl_pv.put(value=self.avg_ampl, timeout=1.0)
        self.fwhm_pv.put(value=self.avg_fwhm, timeout=1.0)  # COMMENT THIS LINE IF TESTING
        self.flt_pos_fs_pv.put(value=self.avg_error, timeout=1.0)
        # apply correction
        self.fb_direction = self.fb_direction_pv.get(timeout=1.0)  # pull correction direction
        self.fb_gain = self.fb_gain_pv.get(timeout=1.0)  # pull gain PV value
        self.on_off = self.on_off_pv.get(timeout=1.0)
        self.correction = (self.avg_error / 1000000) * self.fb_direction * self.fb_gain  # scale from fs to ns and apply direction and gain
        self.atm_fb = self.atm_fb + self.correction  # ATM FB offset is a steady state offset (in other words, target time is not updated), so the feedback offset must be updated progressively
        if (self.on_off == 1) and ((abs(self.correction) < 0.0015)):  # check if drift correction has been turned on and limit corrections to 1.5 ps
            self.atm_fb_pv.put(value=self.atm_fb, timeout=1.0)  # write to correction PV
        else:
            pass
        # additional print statement for rapid debugging
        self.debug_mode = self.debug_mode_pv.get(timeout=1.0)
        if (self.debug_mode == 1):  # keep debug mode turned off when using tester script
            print('Most recent correction value in fs: ', self.correction * 1000000)

def run():
    correction = drift_correction()  # initialize
    heartbeat_counter = 0
    try:
        while True:
            # Update heartbeat
            heartbeat_counter += 1
            correction.heartbeat_pv.put(value=heartbeat_counter, timeout=1.0)

            correction.correct()  # pull data and filter, then apply correction
            time.sleep(0.1)  # keep loop from spinning too fast
    except KeyboardInterrupt:
        print("Script terminated by user.")


if __name__ == "__main__":
    run()