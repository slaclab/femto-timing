import os
from psp.Pv import Pv
import json

class drift_correction():
    """Takes the ATM error PV, filters according to known laser/x-rays params, and apply an offset via the laser lockers HLA."""
    def __init__(self):
        self.name = 'crixs'  # when changing between hutches, this is the only line of code that should need to change
        self.file_path = os.path.abspath(__file__)  # pull current file path
        self.path = os.path.dirname(self.file_path)  # pull current directory
        self.config = self.path+self.name+'_atm_fb.json'  # config file with hutch and locker specific PV names
        # load JSON file
        try:
            with open(self.config, 'r') as file:
                self.sys_config = json.load(file)  # load PVs for current hutch and laser locker
        except json.JSONDecodeError as e:  # check that the json file syxtax is correct
            print('Invalid JSON syntax: '+e)
        # pull PV names from JSON file
        atm_err_pv_nm = str(self.sys_config['tt_pv'])
        atm_fb_pv_nm = str(self.sys_config['atm_fb'])
        # create PV objects
        self.atm_err_pv = Pv(atm_err_pv_nm)  # timetool waveform PV from the DAQ
        self.atm_fb_pv = Pv(atm_fb_pv_nm)  # hook for ATM feedback in laser locker HLA
        self.ampl_pv = Pv('LAS:UNDS:FLOAT:60')  # edge amplitude
        self.flt_pos_pv = Pv('LAS:UNDS:FLOAT:61')  # position in pixels?
        self.flt_pos_ps_pv = Pv('LAS:UNDS:FLOAT:62')  # position in ps
        # connect to PVs
        self.atm_err_pv.connect(timeout = 1.0) 
        self.atm_fb_pv.connect(timeout = 1.0)
        self.ampl_pv.connect(timeout = 1.0)
        self.flt_pos_pv.connect(timeout = 1.0)
        self.flt_pos_ps_pv.connect(timeout = 1.0)

        

    def filter(self):
        """Takes ATM waveform PV data, applies filtering to detemine valid error values, and applies a correction to laser locker HLA."""
        self.atm_err = self.atm_err_pv.get(ctrl = True, timeout = 1.0)  # get current timetool waveform PV values from the DAQ
        # unpack useful filtering parameters from waveform
        self.ampl = self.atm_err[0]
        self.flt_pos = self.atm_err[1]
        self.flt_pos_ps = self.atm_err[2]
        # write useful filtering parameters to individual PVs for easier monitoring
        self.ampl_pv.put(self.ampl)
        self.flt_pos_pv.put(self.flt_pos)
        self.flt_pos_ps_pv.put(self.flt_pos_ps)
        


def run():
    correction = drift_correction() # initialize
    error = False
    while error==False:
        try:
            correction.filter() # pull data and filter, then apply correction
        except:

