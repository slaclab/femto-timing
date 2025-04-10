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
            IPM_Name = 'XCS:SB1:BMMON:SUM' # intensity profile monitor PV
            
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
        self.Drift_Correct_PV = dict()  # will hold list of IOC pvs
        self.values = dict() # will hold the numbers from the time tool
        self.limits = dict() # will hold limits from matlab pvs
        self.old_values = dict() # will hold the old values read from matlab
        self.Drift_Correct = dict()
        self.Name = ['Watchdog', 'pix', 'fs', 'amp', 'amp_second', 'ref', 'FWHM', 'Stage', 'ipm', 'dcsignal', 'Script Enabled?', 'IPM Good?', 'Amplitude Good?', 'FWHM Good?', 'Good TT Measurement?'] #list of internal names
        self.Drift_Correct_PV[0] = Dev_Base+'WATCHDOG'
        self.Drift_Correct_PV[1] = Dev_Base+'PIX'
        self.Drift_Correct_PV[2] = Dev_Base+'FS'
        self.Drift_Correct_PV[3] = Dev_Base+'AMP'
        self.Drift_Correct_PV[4] = Dev_Base+'AMP_SEC'
        self.Drift_Correct_PV[5] = Dev_Base+'REF'
        self.Drift_Correct_PV[6] = Dev_Base+'FWHM'
        self.Drift_Correct_PV[7] = Dev_Base+'STAGE'
        self.Drift_Correct_PV[8] = Dev_Base+'IPM'
        self.Drift_Correct_PV[9] = Dev_Base+'DRIFT_CORRECT_SIG'
        self.Drift_Correct_PV[10]= Dev_Base+'matlab:10'
        self.Drift_Correct_PV[11]= Dev_Base+'matlab:11'
        self.Drift_Correct_PV[12]= Dev_Base+'matlab:12'
        self.Drift_Correct_PV[13]= Dev_Base+'matlab:13'
        self.Drift_Correct_PV[14]= Dev_Base+'matlab:14'

        #print('Value of Watchdog'+self.Drift_Correct_PV[0])
        for n in range(0, len(self.Name)):
            self.Drift_Correct[self.Name[n]] = [Pv(self.Drift_Correct_PV[n]), Pv(self.Drift_Correct_PV[n]+'.LOW'), Pv(self.Drift_Correct_PV[n]+'.HIGH'), Pv(self.Drift_Correct_PV[n]+'.DESC')]
            for x in range(0,4):
                    self.Drift_Correct[self.Name[n]][x].connect(timeout=1.0)  # connnect to all the various PVs.     
            for x in range(0,3):
                self.Drift_Correct[self.Name[n]][x].get(ctrl=True, timeout=1.0)
                self.Drift_Correct[self.Name[n]][3].put(value = self.Name[n], timeout = 1.0)
        self.W = watchdog3.watchdog(self.Drift_Correct[self.Name[0]][0]) # initialize watchdog   

    def read_write(self):   
        self.TTALL_PV.get(ctrl=True, timeout=1.0) # get TT array data
        self.Stage_PV.get(ctrl=True, timeout=1.0) # get TT stage position
        self.IPM_PV.get(ctrl=True, timeout=1.0) # get intensity profile

        self.TT_Script_EN.get(ctrl=True, timeout=1.0)

        for n in range(1, len(self.Name)):
             self.old_values[self.Name[n]] = self.Drift_Correct[self.Name[n]][0].value # old PV values
             #self.limits[self.Name[n]] = [self.Drift_Correct[self.Name[n]][1].value, self.Drift_Correct[self.Name[n]][2].value] # limits
        for n in range (1,7):
            self.Drift_Correct[self.Name[n]][0].put(value = self.TTALL_PV.value[n-1], timeout = 1.0)  # write to matlab PVs
            for x in range(0,3):
                self.Drift_Correct[self.Name[n]][x].get(ctrl=True, timeout=1.0)  # get all the matlab pvs
        self.Drift_Correct[self.Name[7]][0].put(value = self.Stage_PV.value, timeout = 1.0)  # read stage position
        self.Drift_Correct[self.Name[8]][0].put(value = self.IPM_PV.value, timeout = 1.0) # read/write intensity profile

        # Script Enabled?
        if( self.TT_Script_EN.value == 1):
            self.Drift_Correct[self.Name[10]][0].put(value = self.TT_Script_EN.value, timeout = 1.0)
            time.sleep(0.1)
        else:
            self.Drift_Correct[self.Name[10]][0].put(value = 0, timeout = 1.0)
            print('Time Tool Script Disabled')
            time.sleep(3)

        #if ( self.IPM_PV.value > self.Drift_Correct['ipm'][1].value ) and (self.IPM_PV.value < self.Drift_Correct['ipm'][2].value ):
        # Good signal in Intensity Profile Monitor?
        if( self.IPM_PV.value > 500):
            self.Drift_Correct[self.Name[11]][0].put(value = self.TT_Script_EN.value, timeout = 1.0)
            time.sleep(0.1)
        else:
            self.Drift_Correct[self.Name[11]][0].put(value = 0, timeout = 1.0)
            print('Low Signal in IPM')
            time.sleep(1)

        # if ( self.Drift_Correct['amp'][0].value > self.Drift_Correct['amp'][1].value ) and ( self.Drift_Correct['amp'][0].value < self.Drift_Correct['amp'][2].value ):
        # Good Amplitude in Time Tool?
        if( self.Drift_Correct[self.Name[3]][0].value > 0.02):
            self.Drift_Correct[self.Name[12]][0].put(value = self.TT_Script_EN.value, timeout = 1.0)
            time.sleep(0.1)
        else:
            self.Drift_Correct[self.Name[12]][0].put(value = 0, timeout = 1.0)
            print('Low Amplitude in Time Tool')
            time.sleep(1)

        # Is FWHM Within the Range?
        if( 30 < self.Drift_Correct[self.Name[6]][0].value < 250):
            self.Drift_Correct[self.Name[13]][0].put(value = self.TT_Script_EN.value, timeout = 1.0)
            time.sleep(0.1)
        else:
            self.Drift_Correct[self.Name[13]][0].put(value = 0, timeout = 1.0)
            print('FWHM Outside the Range')
            time.sleep(1)

        # Is it a Good Measurement?
        if (self.Drift_Correct[self.Name[11]][0] == 1 and 
            self.Drift_Correct[self.Name[12]][0] == 1 and 
            self.Drift_Correct[self.Name[13]][0] == 1 and 
            self.Drift_Correct[self.Name[11]][0] == 1):
            self.Drift_Correct[self.Name[14]][0].put(value = self.TT_Script_EN.value, timeout = 1.0)
            time.sleep(0.1)
        else:
            self.Drift_Correct[self.Name[14]][0].put(value = 0, timeout = 1.0)
            print('Not a Good Measurement')
            time.sleep(1)

"""         ###
         #print self.TTALL_PV.value
         #print 'stage position' # TEMP
         #print self.Stage_PV.value # TEMP
         #print 'intensity profile sum'
         #print self.IPM_PV.value

         # need to decide whether to output to the drift correction signal
         # 1. IPM must be in range
        if ( self.IPM_PV.value > self.Drift_Correct['ipm'][1].value ) and (self.IPM_PV.value < self.Drift_Correct['ipm'][2].value ):
             #print 'intensity profile good'
             # 2. amp must be in range
             if ( self.Drift_Correct['amp'][0].value > self.Drift_Correct['amp'][1].value ) and ( self.Drift_Correct['amp'][0].value < self.Drift_Correct['amp'][2].value ):
                 #print 'TT edge fit good'
                 # 3. pix must be different from last pix, and stage must not be moving
                 if ( self.Drift_Correct['fs'][0].value != self.old_values['fs'] ) and ( self.Drift_Correct['Stage'][0].value == self.old_values['Stage'] ):
                     #print 'Data is fresh. New pix value:'
                     #print self.Drift_Correct['pix'][0].value
                     # at this point, know that data is good and need to move it over to the drift correction algo
                     # self.Drift_Correct['dcsignal'][0].put(value = self.Drift_Correct['pix'][0].value, timeout = 1.0)
                     self.Drift_Correct['dcsignal'][0].put(value = self.Drift_Correct['fs'][0].value, timeout = 1.0)
                     # dvc Test
                 #else:
                     #print 'Data is stale or stage is moving'
                     #print self.old_values['pix']
                     #print self.Drift_Correct['pix'][0].value
             #else:
                 #print 'TT edge fit bad'
         #else:
             #print 'intensity profile bad'
"""

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
