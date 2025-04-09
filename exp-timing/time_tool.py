#time_tool.py
import time
import numpy as np
import watchdog3
from psp.Pv import Pv
import sys

class time_tool():
    def __init__ (self, sys='NULL'): 
        if sys == 'FS11': # set up for new bay 1 laser
            print('starting FS11')
            self.delay = 0.1
            TTALL_Name = 'XPP:TIMETOOL:TTALL'  # time tool array name
            Dev_Base = 'LAS:FS11:VIT:'  
            Stage_Name = 'XPP:LAS:MMN:16'  # delay stage for time tool
            IPM_Name = 'XPP:SB2:BMMON:SUM' # intensity profile monitor PV
        elif sys == 'FS14':  # set up FS14 system
            print('Starting FS14')
            self.delay = 0.1 # 1 second delay
            #TTALL_Name = 'TMO:TIMETOOL:TTALL'  # time tool array name
            Dev_Base = 'LAS:FS14:VIT:'
            #Stage_Name = 'LM1K4:COM_MP2_DLY1'  # delay stage for time tool
            #IPM_Name = 'EM2K0:XGMD:HPS:milliJoulesPerPulse' # intensity profile monitor PV
            
            print('Borrow CXI PVs to monitor')
            TTALL_Name = 'XCS:TT:01:TTALL' #time tool array name
            Stage_Name = 'CXI:LAS:MMN:01'  # delay stage for time tool
            IPM_Name = 'CXI:DG2:BMMON:SUM' # intensity profile monitor PV
            
            print('Exit FS14 elif')
        elif sys == 'XPP':  # set up xpp system
            print('starting XPP')
            self.delay = 0.1 # 1 second delay
            TTALL_Name = 'XPP:TIMETOOL:TTALL'  # time tool array name
            Dev_Base = 'LAS:FS3:VIT:'
            Stage_Name = 'XPP:LAS:MMN:16'  # delay stage for time tool
            IPM_Name = 'XPP:SB2:BMMON:SUM' # intensity profile monitor PV
        elif sys == 'XCS':  # set up xcs system
            print('starting XCS')
            self.delay = 0.1 # 1 second delay
            TTALL_Name = 'XCS:TIMETOOL:TTALL'  # time tool array name
            Dev_Base = 'LAS:FS4:VIT:'
            Stage_Name = 'XCS:LAS:MMN:01'  # delay stage for time tool
            IPM_Name = 'XCS:SB1:BMMON:SUM' # intensity profile monitor PV
        elif sys == 'MFX':  # set up xcs system
            print('starting MFX')
            self.delay = 0.1 # 1 second delay
            TTALL_Name = 'MFX:TT:01:TTALL'  # time tool array name
            Dev_Base = 'LAS:FS45:VIT:'
            Stage_Name = 'MFX:LAS:MMN:06'  # delay stage for time tool
            IPM_Name = 'MFX:DG2:BMMON:SUM' # intensity profile monitor PV
        elif sys == 'CXI':  # set up cxi system
            print('starting CXI')
            self.delay = 0.1 # 1 second delay
            TTALL_Name = 'CXI:TT:01:TTALL' #time tool array name
            Dev_Base = 'LAS:FS5:VIT:'
            Stage_Name = 'CXI:LAS:MMN:01'  # delay stage for time tool
            #Stage_Name = 'CXI:USR:MMN:25'  # delay stage for time tool
            IPM_Name = 'CXI:DG2:BMMON:SUM' # intensity profile monitor PV
        else:
            print(sys+' not found, exiting')
            exit()
        
        print('Script PV 1')
        self.TT_Script_EN = Pv(Dev_Base+'matlab:31')
        self.TT_Script_EN.connect(timeout=1.0) # connect to pv
        
        self.TTALL_PV = Pv(TTALL_Name)
        self.TTALL_PV.connect(timeout=1.0) # connect to pv
        self.Stage_PV = Pv(Stage_Name)
        self.Stage_PV.connect(timeout=1.0)
        self.IPM_PV = Pv(IPM_Name)
        self.IPM_PV.connect(timeout=1.0)
        self.drift_correct_pv = dict()  # will hold list of IOC pvs
        self.values = dict() # will hold the numbers from the time tool
        self.limits = dict() # will hold limits from matlab pvs
        self.old_values = dict() # will hold the old values read from matlab
        self.drift_correct = dict()
        self.nm = ['Watchdog', 'pix', 'fs', 'amp', 'amp_second', 'ref', 'FWHM', 'Stage', 'ipm', 'dcsignal', 'MATLAB10'] #list of internal names
        self.drift_correct_pv[0] = Dev_Base+'WATCHDOG'
        self.drift_correct_pv[1] = Dev_Base+'PIX'
        self.drift_correct_pv[2] = Dev_Base+'FS'
        self.drift_correct_pv[3] = Dev_Base+'AMP'
        self.drift_correct_pv[4] = Dev_Base+'AMP_SEC'
        self.drift_correct_pv[5] = Dev_Base+'REF'
        self.drift_correct_pv[6] = Dev_Base+'FWHM'
        self.drift_correct_pv[7] = Dev_Base+'STAGE'
        self.drift_correct_pv[8] = Dev_Base+'IPM'
        self.drift_correct_pv[9] = Dev_Base+'DRIFT_CORRECT_SIG'
        self.drift_correct_pv[10]= Dev_Base+'matlab:10'

        #print('Value of Watchdog'+self.drift_correct_pv[0])
        for n in range(0, len(self.nm)):
            self.drift_correct[self.nm[n]] = [Pv(self.drift_correct_pv[n]), Pv(self.drift_correct_pv[n]+'.LOW'), Pv(self.drift_correct_pv[n]+'.HIGH'), Pv(self.drift_correct_pv[n]+'.DESC')]
            for x in range(0,4):
                    self.drift_correct[self.nm[n]][x].connect(timeout=1.0)  # connnect to all the various PVs.     
            for x in range(0,3):
                self.drift_correct[self.nm[n]][x].get(ctrl=True, timeout=1.0)
                self.drift_correct[self.nm[n]][3].put(value = self.nm[n], timeout = 1.0)
        self.W = watchdog3.watchdog(self.drift_correct[self.nm[0]][0]) # initialize watchdog   

    def read_write(self):   
        self.TTALL_PV.get(ctrl=True, timeout=1.0) # get TT array data
        self.Stage_PV.get(ctrl=True, timeout=1.0) # get TT stage position
        self.IPM_PV.get(ctrl=True, timeout=1.0) # get intensity profile

        self.TT_Script_EN.get(ctrl=True, timeout=1.0)

        for n in range(1, len(self.nm)):
             self.old_values[self.nm[n]] = self.drift_correct[self.nm[n]][0].value # old PV values
             #self.limits[self.nm[n]] = [self.drift_correct[self.nm[n]][1].value, self.drift_correct[self.nm[n]][2].value] # limits
        if n in range (1,6):
            self.drift_correct[self.nm[n]][0].put(value = self.TTALL_PV.value[n-1], timeout = 1.0)  # write to matlab PVs
            print('Yes if')
            for x in range(0,3):
                self.drift_correct[self.nm[n]][x].get(ctrl=True, timeout=1.0)  # get all the matlab pvs
        else:
            print('No if')
        self.drift_correct[self.nm[7]][0].put(value = self.Stage_PV.value, timeout = 1.0)  # read stage position
        self.drift_correct[self.nm[8]][0].put(value = self.IPM_PV.value, timeout = 1.0) # read/write intensity profile
        
         ###
         #print self.TTALL_PV.value
         #print 'stage position' # TEMP
         #print self.Stage_PV.value # TEMP
         #print 'intensity profile sum'
         #print self.IPM_PV.value

         # need to decide whether to output to the drift correction signal
         # 1. IPM must be in range
        if ( self.IPM_PV.value > self.drift_correct['ipm'][1].value ) and (self.IPM_PV.value < self.drift_correct['ipm'][2].value ):
             #print 'intensity profile good'
             # 2. amp must be in range
             if ( self.drift_correct['amp'][0].value > self.drift_correct['amp'][1].value ) and ( self.drift_correct['amp'][0].value < self.drift_correct['amp'][2].value ):
                 #print 'TT edge fit good'
                 # 3. pix must be different from last pix, and stage must not be moving
                 if ( self.drift_correct['fs'][0].value != self.old_values['fs'] ) and ( self.drift_correct['Stage'][0].value == self.old_values['Stage'] ):
                     #print 'Data is fresh. New pix value:'
                     #print self.drift_correct['pix'][0].value
                     # at this point, know that data is good and need to move it over to the drift correction algo
                     # self.drift_correct['dcsignal'][0].put(value = self.drift_correct['pix'][0].value, timeout = 1.0)
                     self.drift_correct['dcsignal'][0].put(value = self.drift_correct['fs'][0].value, timeout = 1.0)
                     # dvc Test
                 #else:
                     #print 'Data is stale or stage is moving'
                     #print self.old_values['pix']
                     #print self.drift_correct['pix'][0].value
             #else:
                 #print 'TT edge fit bad'
         #else:
             #print 'intensity profile bad'
        if( self.TT_Script_EN.value == 1):
            print('Do a correction!')
            self.drift_correct[self.nm[10]][0].put(value = self.TT_Script_EN.value, timeout = 1.0)
            #self.drift_correct_pv[0] = self.drift_correct_pv[0] + 1
            time.sleep(1)
        else:
            print('No correction')
            time.sleep(1)
            print('sleeping')
            self.drift_correct[self.nm[10]][0].put(value = 0, timeout = 1.0)
            

def run():  # just a loop to keep recording         
    if len(sys.argv) < 2:
        T = time_tool()  # initialize
        print('exit initialize')
    else:
        T = time_tool(sys.argv[1])
    print('Enter main loop')
    while T.W.error == 0:
        T.W.check() # check / update watchdog counter
        time.sleep(T.delay)
        try:
            T.read_write()  # collects the data
        except:
            del T
            print('Crashed, restarting')
            T = time_tool() # create again
            if T.W.error:
                return        
    pass  

if __name__ == "__main__":
   run()
