#time_tool.py
import time
import numpy as np
import watchdog3
from psp.Pv import Pv
import sys

class time_tool():
    def __init__ (self, sys='NULL'):

        self.IPM_Threshold = 500.0
        self.Amplitude_Threshold = 0.02
        self.Drift_Adjustment_Threshold = 0.05
        self.FWHM_Threshold_Low = 30.0
        self.FWHM_Threshold_High = 250.0
        #self.fwhm_threshs: Tuple[float, float] = (30, 130)
        self.Number_Events = 61
        self.TimeTool_Edges = np.zeros([self.Number_Events])
        self.delay = 0.1

        if sys == 'FS11': # set up for new bay 1 laser
            print('starting FS11')
            TTALL_Name = 'XPP:TIMETOOL:TTALL'  # time tool array name
            Dev_Base = 'LAS:FS11:VIT:'  
            Stage_Name = 'XPP:LAS:MMN:16'  # delay stage for time tool
            IPM_Name = 'XPP:SB2:BMMON:SUM' # intensity profile monitor PV

        elif sys == 'FS14':  # set up FS14 system
            print('Starting FS14')
            #TTALL_Name = 'TMO:TIMETOOL:TTALL'  # time tool array name
            Dev_Base = 'LAS:FS14:VIT:'
            #Stage_Name = 'LM1K4:COM_MP2_DLY1'  # delay stage for time tool
            #IPM_Name = 'EM2K0:XGMD:HPS:milliJoulesPerPulse' # intensity profile monitor PV

            print('Borrow PVs to monitor')
            TTALL_Name = 'XCS:TT:01:TTALL' #time tool array name
            Stage_Name = 'CXI:LAS:MMN:01'  # delay stage for time tool
            IPM_Name = 'CXI:DG2:BMMON:SUM' # intensity profile monitor PV
            self.IPM_Threshold = 10.0 #500
            self.Amplitude_Threshold = 0.01

        elif sys == 'XPP':  # set up xpp system
            print('starting XPP')
            TTALL_Name = 'XPP:TIMETOOL:TTALL'  # time tool array name
            Dev_Base = 'LAS:FS3:VIT:'
            Stage_Name = 'XPP:LAS:MMN:16'  # delay stage for time tool
            IPM_Name = 'XPP:SB2:BMMON:SUM' # intensity profile monitor PV
        elif sys == 'XCS':  # set up xcs system
            print('starting XCS')
            TTALL_Name = 'XCS:TIMETOOL:TTALL'  # time tool array name
            Dev_Base = 'LAS:FS4:VIT:'
            Stage_Name = 'XCS:LAS:MMN:01'  # delay stage for time tool
            IPM_Name = 'XCS:SB1:BMMON:SUM' # intensity profile monitor PV
        elif sys == 'MFX':  # set up xcs system
            print('starting MFX')
            TTALL_Name = 'MFX:TT:01:TTALL'  # time tool array name
            Dev_Base = 'LAS:FS45:VIT:'
            Stage_Name = 'MFX:LAS:MMN:06'  # delay stage for time tool
            IPM_Name = 'MFX:DG2:BMMON:SUM' # intensity profile monitor PV
        elif sys == 'CXI':  # set up cxi system
            print('starting CXI')
            TTALL_Name = 'CXI:TT:01:TTALL' #time tool array name
            Dev_Base = 'LAS:FS5:VIT:'
            Stage_Name = 'CXI:LAS:MMN:09'  # delay stage for time tool
            #Stage_Name = 'CXI:USR:MMN:01'  # delay stage for time tool
            IPM_Name = 'CXI:DG2:BMMON:SUM' # intensity profile monitor PV
        else:
            print(sys+' not found, exiting')
            exit()

        self.TTALL_PV = Pv(TTALL_Name)
        self.TTALL_PV.connect(timeout=1.0) # connect to pv
        self.Stage_PV = Pv(Stage_Name)
        self.Stage_PV.connect(timeout=1.0)
        self.IPM_PV = Pv(IPM_Name)
        self.IPM_PV.connect(timeout=1.0)
        self.TT_Script_EN = Pv(Dev_Base+'matlab:31')
        self.TT_Script_EN.connect(timeout=1.0) # connect to pv
        #self.values = dict() # will hold the numbers from the time tool
        #self.limits = dict() # will hold limits from matlab pvs
        #self.old_values = dict() # will hold the old values read from matlab
        self.Drift_Correct = dict()
        self.Drift_Correct_PV = dict()  # will hold list of IOC pvs
        self.Name = ['Watchdog', 'pix', 'Edge Position', 'Amplitude', 'amp_second', 'ref', 'FWHM', 'Stage', 'IPM', 'Drift Correction P', 'Drift Correction Value', 'IPM Good?', 'Amplitude Good?', 'FWHM Good?', 'Good TT Measurement?'] #list of internal names
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
        self.Drift_Correct_PV[10]= Dev_Base+'DRIFT_CORRECT_VAL'
        self.Drift_Correct_PV[11]= Dev_Base+'matlab:11'
        self.Drift_Correct_PV[12]= Dev_Base+'matlab:12'
        self.Drift_Correct_PV[13]= Dev_Base+'matlab:13'
        self.Drift_Correct_PV[14]= Dev_Base+'matlab:14'

        for n in range(0, len(self.Name)):
            self.Drift_Correct[self.Name[n]] = [Pv(self.Drift_Correct_PV[n]), Pv(self.Drift_Correct_PV[n]+'.LOW'), Pv(self.Drift_Correct_PV[n]+'.HIGH'), Pv(self.Drift_Correct_PV[n]+'.DESC')]
            for x in range(0,4):
                    self.Drift_Correct[self.Name[n]][x].connect(timeout=1.0)  # connnect to all the various PVs.     
            for x in range(0,3):
                self.Drift_Correct[self.Name[n]][x].get(ctrl=True, timeout=1.0)
            self.Drift_Correct[self.Name[n]][3].put(value = self.Name[n], timeout = 1.0)
        self.W = watchdog3.watchdog(self.Drift_Correct[self.Name[0]][0]) # initialize watchdog   

    def read_write(self):

        self.TT_Script_EN.get(ctrl=True, timeout=1.0)
        Run_TT_Script = 'Enabled' if self.TT_Script_EN.value == 1 else 'Disabled'
        
        # Use this TT Script to Correct Drift?
        if self.TT_Script_EN.value == 1:
            Edge_Count: int = 0
            time_last_good_val: float = time.time()
            print(f'The Time Tool Script is {Run_TT_Script}')

            while Edge_Count < self.Number_Events:

                self.TTALL_PV.get(ctrl=True, timeout=1.0) # get TT array data
                self.Stage_PV.get(ctrl=True, timeout=1.0) # get TT stage position
                self.IPM_PV.get(ctrl=True, timeout=1.0) # get intensity profile

                for n in range (1,7):
                    self.Drift_Correct[self.Name[n]][0].put(value = self.TTALL_PV.value[n-1], timeout = 1.0)  # write to matlab PVs
                self.Drift_Correct[self.Name[7]][0].put(value = self.Stage_PV.value, timeout = 1.0)  # read stage position
                self.Drift_Correct[self.Name[8]][0].put(value = self.IPM_PV.value, timeout = 1.0) # read/write intensity profile
                for n in range (1, 11):
                    self.Drift_Correct[self.Name[n]][0].get(ctrl=True, timeout = 1.0)

                # Good signal in Intensity Profile Monitor?
                self.Drift_Correct[self.Name[11]][0].put(value=int(self.Drift_Correct[self.Name[8]][0].value > self.IPM_Threshold), timeout=1.0)
                # Good Amplitude in Time Tool?
                self.Drift_Correct[self.Name[12]][0].put(value=int(self.Drift_Correct[self.Name[3]][0].value > self.Amplitude_Threshold), timeout=1.0)
                # Is FWHM Within the Range?
                self.Drift_Correct[self.Name[13]][0].put(value=int(self.FWHM_Threshold_Low < self.Drift_Correct[self.Name[6]][0].value < self.FWHM_Threshold_High), timeout=1.0)

                for n in range (8, 15):
                    self.Drift_Correct[self.Name[n]][0].get(ctrl=True, timeout = 1.0)

                # Is it a Good Measurement?
                if all(self.Drift_Correct[self.Name[i]][0].value == 1 for i in range(11, 14)):
                    #print('Good Measurement!')
                    self.Drift_Correct[self.Name[14]][0].put(value = 1, timeout = 1.0)            
                    #self.Drift_Correct[self.Name[9]][0].put(value = self.Drift_Correct[self.Name[2]][0].value, timeout = 1.0)
                    print(f'Good Measurement! - TT Edge position {self.Drift_Correct[self.Name[2]][0].value:.3f} ps')

                    #NEED TO CHANGE TO EDGE VALUE, [2]
                    self.TimeTool_Edges[Edge_Count] = self.Drift_Correct[self.Name[2]][0].value
                    Edge_Count += 1
                    time_last_good_val = time.time()

                else:
                    self.Drift_Correct[self.Name[14]][0].put(value = 0, timeout = 1.0)
                    #print('Not a Good Measurement')

                if time.time() - time_last_good_val > 30:
                    print(f'No good measurement over one minute. Check thresholds?')
                    break

            print(f'Edge count = {Edge_Count}')
            if Edge_Count == self.Number_Events:
                Edge_Mean = np.mean(self.TimeTool_Edges)
                print(f'Edges Array: [{" ".join(f"{edge:.3f}" for edge in self.TimeTool_Edges)}]')
                print(f'Mean of Edges = {Edge_Mean:.3f}')

                IPM_Good = 'Good' if self.Drift_Correct[self.Name[11]][0].value == 1 else 'Low'
                Amp_Good = 'Good' if self.Drift_Correct[self.Name[12]][0].value == 1 else 'Low'
                FWHM_Good = 'Good' if self.Drift_Correct[self.Name[13]][0].value == 1 else 'Bad'
                print(f'{IPM_Good} Signal in IPM: {self.Drift_Correct[self.Name[8]][0].value:.3f}')
                print(f'{Amp_Good} Amplitude in TT: {self.Drift_Correct[self.Name[3]][0].value:.3f}')
                print(f'{FWHM_Good} FWHM in TT: {self.Drift_Correct[self.Name[6]][0].value:.3f}')

                # Is it the Edge value greater than the threshold?
                if (abs(Edge_Mean) > self.Drift_Adjustment_Threshold):            

                    # Edge_Mean = Edge_Mean * self.Drift_Correct[self.Name[9]][0].value
                    Edge_Mean = Edge_Mean * self.Drift_Correct[self.Name[9]][0].value + self.Drift_Correct[self.Name[10]][0].value
                    print(f'Making adjustment to {Edge_Mean:.3f} ps!')

                    self.Drift_Correct[self.Name[10]][0].put(value = Edge_Mean, timeout = 1.0)
                    # set position of LXT?
                    # lxt.set_current_position(-float(txt.position))

                print('---------------------------------')

        # Do only a single correction for now, disable correction script?
        self.TT_Script_EN.put(value=0, timeout=1.0)
        #self.TT_Script_EN.get(ctrl=True, timeout = 1.0)
        
        if self.Drift_Correct[self.Name[0]][0] % 100 == 0:
            print(f"Value: {print(self.Drift_Correct[self.Name[0]][0].value)} - The time is {time.time()}")
            print(f'The Time Tool Script is {Run_TT_Script}')

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
