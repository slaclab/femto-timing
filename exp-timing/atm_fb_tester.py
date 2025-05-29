import time
import random
from psp.Pv import Pv
import pandas as pd


class atm_fb_tester():
    def __init__(self):
        self.data_path = '/cds/home/r/rlodico/scripts/lcls2-atm-fb-test/exp1016923_run150.csv'  # path to csv where historical data is saved
        # create PV objects
        self.atm_err_ampl_pv = Pv('LAS:UNDS:FLOAT:59')  # PV to hold dummy edge amplitude for testing
        self.atm_err_flt_pos_fs_pv = Pv('LAS:UNDS:FLOAT:58')  # PV to hold dummy fs error for testing
        self.dummy_fb_pv = Pv('LAS:UNDS:FLOAT:68')  # dummy PV for holding correction values written to by crixs_atm_fb.py
        self.accum_err_pv = Pv('LAS:UNDS:FLOAT:69')  # PV for tracking accumulated error during test
        # connect to PVs
        self.atm_err_ampl_pv.connect(timeout=1.0)
        self.atm_err_flt_pos_fs_pv.connect(timeout=1.0)
        self.dummy_fb_pv.connect(timeout=1.0)
        self.accum_err_pv.connect(timeout=1.0)

    def arbitrary_test(self):
        # test set-up
        self.accum_err = 0
        self.accum_dict = dict()  # dictionary to hold accum error after each loop
        self.accum_err_pv.put(self.accum_err)  # reset the error accumulator to 0 at start of test
        self.drift_rate = 200  # drift rate in fs/min
        self.offset = 5198  # real chemRIXS ATM offset in fs
        self.test_duration = 300  # test duration in seconds
        self.correct_prev = (self.dummy_fb_pv.get(timeout=1.0)) * 1000000  # get initial correction value and convert to fs
        self.count = 0
        self.time_prev = time.time()
        self.start_time = time.time()
        # test loop
        while ((time.time() - self.start_time) < self.test_duration):
            self.ampl = random.uniform(20, 80)  # generate random amplitude close to or within the acceptable range
            self.time_elapsed = time.time() - self.time_prev  # calculate seconds since previous correction
            self.time_prev = time.time()  # update previous time for next loop iteration
            self.fixed_err = (self.drift_rate / 60) * self.time_elapsed  # convert to fs/s, then calculate amount of drift since last loop iteration
            self.rand_err = random.uniform(-(self.fixed_err * 0.2), (self.fixed_err * 0.2))  # generate a random number less than 20% the magnitude of the fixed error
            self.comb_err = self.fixed_err + self.rand_err  # new error will be fixed error +/- 20%
            # update dummy timetool PVs
            self.atm_err_ampl_pv.put(self.ampl)
            self.curr_err = self.accum_err_pv.get(timeout=1.0)
            self.total_err = self.curr_err + self.comb_err
            self.atm_err_flt_pos_fs_pv.put(self.total_err + self.offset)  # add in atm offset and write to dummy error PV
            # update error accumulator
            self.accum_err = self.accum_err + self.comb_err
            # if new correction applied, subtract from error accumulator
            self.correct = (self.dummy_fb_pv.get(timeout=1.0)) * 1000000  # convert to fs
            if (self.correct != self.correct_prev):
                self.accum_err = self.accum_err - self.correct
                self.correct_prev = self.correct
            self.accum_dict[self.count] = self.accum_err  # add to dict for end of test stats
            self.accum_err_pv.put(self.accum_err)  # update error accumulator PV
            time.sleep(3.0)
            self.count += 1
        # calculate test statistics
        self.avg_accum_err = sum(abs(self.accum_dict.values())) / len(self.accum_dict)
        self.max_accum_err = max(self.accum_dict.values())
        # print test statistics
        print("Test Statistics: ")
        print("Programmed Drift Rate: ", self.drift_rate, " fs/min")
        print("Average Residual Error: ", self.avg_accum_err, " fs")
        print("Maximum Residual Error: ", self.max_accum_err, " fs")

    def data_test(self):
        # test set-up
        self.accum_err = 0
        self.accum_dict = dict()  # dictionary to hold accum error after each loop
        self.accum_err_pv.put(self.accum_err)  # reset the error accumulator to 0 at start of test
        self.test_duration = 300  # test duration in seconds
        self.count = 0
        # import data
        self.df = pd.read_csv(self.data_path)
        self.ampls = self.df['Amplitude']
        self.data_errs = self.df['Position']
        # start test timers
        self.time_prev = time.time()
        self.start_time = time.time()
        # test loop
        while ((time.time() - self.start_time) < self.test_duration):
            # update dummy edge amplitude PV
            self.ampl = self.ampls[self.count]
            self.atm_err_ampl_pv.put(value=self.ampl, timeout=1.0)
            # calculate new atm error
            self.data_err = (self.data_errs[self.count])  # raw historical error value
            self.correct = (self.dummy_fb_pv.get(timeout=1.0)) * 1000000  # convert to fs
            self.accum_err = self.data_err - self.correct  # total current error is the historical edge position minus the net correction applied
            self.atm_err_flt_pos_fs_pv.put(value=self.accum_err, timeout=1.0)
            # record accumulated error
            self.accum_dict[self.count] = self.accum_err  # add to dict for end of test stats
            self.accum_err_pv.put(self.accum_err)  # update error accumulator PV
            time.sleep(3.0)
            self.count += 1
        # calculate average residual error
        self.avg_accum_err = sum(self.accum_dict.values()) / len(self.accum_dict)
        print("Average Residual Error: ", self.avg_accum_err, " fs")


def run():
    test = atm_fb_tester()  # initialize
    time.sleep(0.5)  # make sure all PVs initialized
    while True:
        print('1 - Arbitrary Drift Test')
        print('2 - Historical Data Drift Test')
        choice = input('Enter the integer corresponding to your desired option: ')
        try:
            choice = int(choice)
            if (choice > 0 and choice < 3):
                break
            else:
                print('Invalid choice. Please select a valid option.')
        except ValueError:
            print('Invalid choice. Please enter the integer corresponding to your desired option.')
    if (choice == 1):
        test.arbitrary_test()
    else:
        test.data_test()


if __name__ == "__main__":
    run()
