#pcav2ttdrift.py
""" Alt. version of drift compensation for laser lockers based on PCAVs.

This script adapts the structure of time_tool.py, replacing the time-tool logic
with a box-car average of the pcav data to drive a feed-forward loop on the
lockers. This uses the same drift correction pv that is defined in femto.py and
time_tool.py for drift compensation. It is possible that the desired drift
compensation approach should include both time tool data and pcav data, the
former being for fast corrections and the latter to account for the minute time
scale drifts that quickly move the laser outside of the time-tool window. In the
event both drift compensation values are needed, then both input hooks should be
set to True, and the drift average will be added to the time tool values that
pass the original time-tool tests.

This is a Python 2 function.
"""
import time
from pylab import *
import watchdog # the local watchdog implementation used throughout the laser locker codebase
from psp.Pv import Pv
import sys
import random  # random number generator for secondary calibration
from scipy.optimize import leastsq # for secondary calibration
import argparse # adding for utility and parsing the toggle states for which system to use
from collections import deque
import pdb

class time_tool():
    def __init__ (self, sys='NULL',usett=False,usepcav=False,debug=False): 
        """ These definitions do not change from the original."""
        if sys == 'XPP':  # set up xpp system ; JM(2/21) - technically deprecated
            print('starting XPP pcav2ttdrift')
            self.delay = 0.1 # 1 second delay
            pvname = 'XPP:TIMETOOL:TTALL'  # time tool array name
            dev_base = 'LAS:FS3:VIT'
            stagename = 'XPP:LAS:MMN:16'  # delay stage for time tool
            ipmname = 'XPP:SB2:BMMON:SUM' # intensity profile monitor PV
            pixscale = 1.0e-6
            pcavset = "HXR"
        elif sys == 'CXI':  # set up cxi system
            print('starting CXI pcav2ttdrift')
            self.delay = 0.1 # 1 second delay
            pvname = 'CXI:TIMETOOL:TTALL'  # time tool array name
            dev_base = 'LAS:FS5:VIT'
            stagename = 'CXI:LAS:MMN:04'  # delay stage for time tool
            ipmname = 'CXI:DG2:BMMON:SUM' # intensity profile monitor PV         
            pixscale = 1.0e-6
            pcavset = "HXR"
        elif sys == 'XCS':  # set up xcs system
            print('starting XCS pcav2ttdrift')
            self.delay = 0.1 # 1 second delay
            pvname = 'XCS:TIMETOOL:TTALL'  # time tool array name
            dev_base = 'LAS:FS4:VIT'
            stagename = 'XCS:LAS:MMN:01'  # delay stage for time tool
            ipmname = 'XCS:SB1:BMMON:SUM' # intensity profile monitor PV
            pixscale = 1.0e-6
            pcavset = "HXR"
        elif sys == 'FS11':  # set up FS11 system
            print('starting FS11 pcav2ttdrift')
            self.delay = 0.1 # 1 second delay
            pvname = 'XPP:TIMETOOL:TTALL'  # time tool array name
            dev_base = 'LAS:FS11:VIT'
            stagename = 'XPP:LAS:MMN:01'  # delay stage for time tool
            ipmname = 'XPP:SB2:BMMON:SUM' # intensity profile monitor PV
            self.pixscale = 2.0e-6
            pcavset = "HXR"
        elif sys == 'FS14':  # set up FS14 system
            print('starting FS14 pcav2ttdrift')
            self.delay = 0.1 # 1 second delay
            pvname = 'TMO:TIMETOOL:TTALL'  # time tool array name
            dev_base = 'LAS:FS14:VIT'
            stagename = 'LM1K4:COM_MP2_DLY1'  # delay stage for time tool
            ipmname = 'EM2K0:XGMD:HPS:milliJoulesPerPulse' # intensity profile monitor PV
            pixscale = 2.0e-6
            pcavset = "SXR"

        else:
            print(sys + '  not found, exiting')
            exit()
        
        self.usett = usett
        self.usepcav = usepcav
        self.debug = debug
        if usett:
            print("Using time tool drift compensation")
        if usepcav:
            print("Using phase cavity drift compensation")
        if debug:
            print("..running in debug mode")
        if pcavset == "HXR":
            pcavpv=['SIOC:UNDH:PT01:0:TIME0','SIOC:UNDH:PT01:0:TIME1'] # PVs for the output time for the two HXR, NC Linac cavities
        elif pcavset == "SXR":
            pcavpv=['SIOC:UNDS:PT01:0:TIME0','SIOC:UNDS:PT01:0:TIME1'] # PVs for the output time for the two SXR beamline, NC Linac cavities
        
        self.ttpv = Pv(pvname)
        self.ttpv.connect(timeout=1.0) # connect to pv
        self.stagepv = Pv(stagename)
        self.stagepv.connect(timeout=1.0)
        self.ipmpv = Pv(ipmname)
        self.ipmpv.connect(timeout=1.0)
        self.pcava=Pv(pcavpv[0])
        self.pcava.connect(timeout=1.0)
        self.pcavb=Pv(pcavpv[1])
        self.pcavb.connect(timeout=1.0)
        self.values = dict() # will hold the numbers from the time tool
        self.pcavdata = dict() # will hold values from the phase cavities
        self.drift_correct_pv = dict() # Will hold list of drift correction IOC PVs
        self.pcavbuffer = deque()
        self.ttbuffer = deque(maxlen=100)
        # for n in range(0,60):
        #     self.pcavbuffer.append(0.0)
        self.dccalc = 0.0
        self.pcavcalc=0.0
        self.limits = dict() # will hold limits from drift correction pvs
        self.old_values = dict() # will hold the old values read from drift correction pvs
        self.nm = ['watchdog', 'pix', 'fs', 'amp', 'amp_second', 'ref', 'FWHM', 'Stage', 'ipm','dcsignal','pcavcomp'] #list of internal names
        self.drift_correct_pv[0] = dev_base+'watchdog'
        self.drift_correct_pv[1] = dev_base+'pix'
        self.drift_correct_pv[2] = dev_base+'fs'
        self.drift_correct_pv[3] = dev_base+'amp'
        self.drift_correct_pv[4] = dev_base+'amp_sec'
        self.drift_correct_pv[5] = dev_base+'ref'
        self.drift_correct_pv[6] = dev_base+'FWHM'
        self.drift_correct_pv[7] = dev_base+'stage'
        self.drift_correct_pv[8] = dev_base+'ipm'
        self.drift_correct_pv[9] = dev_base+'drift_correct_sig'
        for n in range(0,10): # loop over pvs to create'
            self.drift_correct[self.nm[n]] = [Pv(self.drift_correct_pv[n]), Pv(self.drift_correct_pv[n]+'.LOW'), Pv(self.drift_correct_pv[n]+'.HIGH'), Pv(self.drift_correct_pv[n]+'.DESC')]
            for x in range(0,4):
                self.drift_correct[self.nm[n]][x].connect(timeout=1.0)  # connnect to all the various PVs.     
            for x in range(0,3):
                self.drift_correct[self.nm[n]][x].get(ctrl=True, timeout=1.0)
                self.drift_correct[self.nm[n]][3].put(value = self.nm[n], timeout = 1.0)
        self.W = watchdog.watchdog(self.drift_correct[self.nm[0]][0]) # initialize watcdog
        if self.usepcav:
            self.pcava.get(ctrl=True, timeout=1.0)
            self.pcavb.get(ctrl=True, timeout=1.0)
            #pdb.set_trace()
            self.pcavinitial = (self.pcava.value+self.pcavb.value)/2.0
            self.old_values['pcavcomp'] = 0.0
            self.drift_correct['pcavcomp'][0].put(value=0.0, timeout=1.0)
            #pdb.set_trace()
            self.pcavscale = -0.0008439

        
    def read_write(self):
        #pdb.set_trace()
        if self.usett:
            self.ttpv.get(ctrl=True, timeout=1.0) # get TT array data
            self.stagepv.get(ctrl=True, timeout=1.0) # get TT stage position
            self.ipmpv.get(ctrl=True, timeout=1.0) # get intensity profile
            for n in range(1,9):
                self.old_values[self.nm[n]] = self.drift_correct_pv[self.nm[n]][0].value # old PV values
                if n in range(1,6):
                    self.drift_correct_pv[self.nm[n]][0].put(value = self.ttpv.value[n-1], timeout = 1.0)  # write to drift correction PVs 
                for x in range(0,3):
                    self.drift_correct_pv[self.nm[n]][x].get(ctrl=True, timeout=1.0)  # get all the drift correction pvs
            self.drift_correct_pv[self.nm[7]][0].put(value = self.stagepv.value, timeout = 1.0)  # read stage position
            self.drift_correct_pv[self.nm[8]][0].put(value = self.ipmpv.value, timeout = 1.0) # read/write intensity profile
        #pdb.set_trace()
        if self.usepcav:
            self.pcava.get(ctrl=True, timeout=1.0)
            self.pcavb.get(ctrl=True, timeout=1.0)
            self.drift_correct_pv['pcavcomp'][0].get(ctrl=True, timeout=1.0)
            self.old_values['pcavcomp'] = float(self.drift_correct_pv['pcavcomp'][0].value) # old PV values
        #pdb.set_trace()
        if self.usett:
            if (self.ipmpv.value > self.drift_correct_pv['ipm'][1].value) and (self.ipmpv.value < self.drift_correct_pv['ipm'][2].value):
                if ( self.drift_correct_pv['amp'][0].value > self.drift_correct_pv['amp'][1].value ) and ( self.drift_correct_pv['amp'][0].value < self.drift_correct_pv['amp'][2].value ):
                    if ( self.drift_correct_pv['pix'][0].value <> self.old_values['pix'] ) and ( self.drift_correct_pv['Stage'][0].value == self.old_values['Stage'] ):
                        if self.ttbuffer.__len__() >99:
                            self.dccalc = float(mean(self.ttbuffer)*self.pixscale)
                        self.ttbuffer.append(self.drift_correct_pv['pix'][0].value)
                        #self.dccalc = float(self.drift_correct_pv['pix'][0].value*self.pixscale)
                        # self.drift_correct_pv['dcsignal'][0].put(value = self.drift_correct_pv['pix'][0].value, timeout = 1.0)
        #pdb.set_trace()
        if self.usepcav:
            if self.pcavbuffer.__len__() >= 600:
                #pdb.set_trace()
                self.pcavbuffer.popleft()
            self.pcavbuffer.append((self.pcava.value+self.pcavb.value)/2.0-self.pcavinitial)
            # self.pcavcalc = mean(self.pcavbuffer)-self.old_values['pcavcomp']
            self.pcavcalc = mean(self.pcavbuffer)*self.pcavscale
            self.drift_correct_pv['pcavcomp'][0].put(value = mean(self.pcavbuffer), timeout=1.0)
        else:
            self.pcavcalc = 0.0
        if self.debug:
            print('tt + pcav: %f'%(self.dccalc+self.pcavcalc))
        else:
            self.drift_correct_pv['dcsignal'][0].put(value = float(self.dccalc)+float(self.pcavcalc), timeout = 1.0)




def run():  # just a loop to keep recording  
    if len(sys.argv) < 2:
        T = time_tool()  # initialize
    else:
        T = time_tool(args.system,usett=args.timetool,usepcav=args.pcav,debug=args.debug)
    while T.W.error == 0:
        T.W.check() # check / update watchdog counter
        pause(T.delay)
        try:
            T.read_write()  # collects the data 
        except Exception as e:
            print(e)
            del T
            print('crashed, restarting')
            T = time_tool(args.system,usett=args.timetool,usepcav=args.pcav,debug=args.debug) # create again
            if T.W.error:
                return        
    pass  

if __name__ == "__main__":
    #parser
    parser = argparse.ArgumentParser(description = 'Alt. version of drift compensation for laser lockers based on PCAVs.')
    parser.add_argument('system', type=str, help="Identifier for the target hutch")
    parser.add_argument("-T", "--timetool", action='store_true',help="enable time tool contribution to drift comp")
    parser.add_argument("-P", "--pcav", action='store_true',help="enable pcav contribution to drift comp")
    parser.add_argument("-D", "--debug", action="store_true",help="Print desired moves, but do not execute")
    args = parser.parse_args()
    run()
