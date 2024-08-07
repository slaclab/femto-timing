
import time
import math
import numpy as np
import watchdog
from psp.Pv import Pv
import sys
import random
import json
import logging

class PVS():
    """Initializes dictionaries for a particular locker, reads and writes to PVs from that locker."""
    def __init__(self, nx='NULL'):
        """Assigns IOC PVs to dictionaries for each locker parameter for the selected laser system."""
        self.version = 'Watchdog 141126a' #Version string
        self.name = nx # Sets the hutch name
        print(self.name)
        logging.basicConfig(
                format='%(asctime)s - %(levelname)s - %(message)s',
                style='%',
                datefmt='%Y-%m-%d %H:%M',
                level=logging.DEBUG,
                filename=str('/reg/d/iocData/py-fstiming-'+self.name+'/iocInfo/femto.log'),
                filemode='a',
            )
        logging.info('Hutch: %s. IOC Enabled/Rebooted.', self.name)
        self.path = '/cds/group/laser/timing/femto-timing/dev/exp-timing/'
        self.config = self.path+self.name+'_locker_config.json' #Sets name of hutch config file
        namelist = set() # Checks if scripts is configured to run specified locker name
        self.pvlist = dict()  # List of all PVs
        self.PV_errs = dict() # List of PV connection errors
        self.err_idx = 0
        counter_base = dict()  # Time interval counter names
        freq_counter = dict() # Frequency counter names
        dev_base = dict() # dev_base is a combination of the locker name of the subsequent string in the IOC PV sub-name (i.e. 'VIT' in most of the LCLS-I laser lockers)
        phase_motor = dict() # Phase motor names
        laser_trigger = dict() # EVR on time trigger PV        
        error_pv_name = dict() # femto.py script error status for each locker   
        use_drift_correction = dict() # Allows drift correction feature to be turned on/off individually for each locker
        drift_correction_signal = dict() # Drift correction float value in ps pulled from the time_tool.py script
        drift_correction_value = dict() # Current drift correction output in ns
        drift_correction_offset = dict() # Fixed offset in ns applied to the drift_correction_signal value
        drift_correction_gain = dict() # Multiplier applied to drift_correction_signal. Gain of 0 disables drift correction feedback
        drift_correction_dir = dict()  # Bool value that is configurable based on the set-up of the timetool stage in a particular hutch 
        drift_correction_smoothing = dict()  # Smoothing factor that reduces the drift correction step size
        drift_correction_accum = dict() # Enables/disables drift correction accumulation (integration term)
        bucket_correction_delay = dict() # Tracks the amount of time between bucket jump detection and correction
        move_delay = dict()
        script_loop_time = dict() # Tracks the cycle time of one main program loop
        for n in range(0,20):
            use_drift_correction[n] = False  # Turn off except where needed
        use_dither = dict() # Used to allow fast dither of timing
        dither_level = dict()  # Amount of dither in ps
        for n in range(0,20):
            use_dither[n] = False  # Turn off except where needed
        version_pv_name = dict()
        timeout = 1.0  # Default timeout for connecting to PVs

        try:
            with open(self.config, 'r') as file:
                self.locker_config = json.load(file) # Load parameters of current locker from json file
        except json.JSONDecodeError as e: # Check that json file syntax is correct
            print('Invalid JSON syntax: '+e)
            logging.error('Invalid JSON syntax: %s', e)

        # Pull locker configuration data from .json file
        nm = str(self.locker_config['nm'])
        namelist.add(nm)
        base = str(self.locker_config['base'])
        dev_base[nm] = str(base+'VIT:')
        counter_base[nm] = base+'CNT:TI:'   # PV name for the Time Interval Counter (SR620)
        freq_counter[nm] = dev_base[nm]+'FREQ_CUR'        
        phase_motor[nm] = base+'MMS:PH' 
        error_pv_name[nm] = dev_base[nm]+'FS_STATUS' 
        version_pv_name[nm] = dev_base[nm]+'FS_WATCHDOG.DESC'
        laser_trigger[nm] = str(self.locker_config['laser_trigger'])
        drift_correction_signal[nm] = dev_base[nm]+'DRIFT_CORRECT_SIG'
        drift_correction_value[nm] = dev_base[nm]+'DRIFT_CORRECT_VAL'
        drift_correction_offset[nm] = dev_base[nm]+'DRIFT_CORRECT_OFF'
        drift_correction_gain[nm] = dev_base[nm]+'DRIFT_CORRECT_GAIN'
        drift_correction_dir[nm] = self.locker_config['drift_correction_dir']
        drift_correction_smoothing[nm] = dev_base[nm]+'DRIFT_CORRECT_SMOOTH'
        drift_correction_accum[nm] = dev_base[nm]+'DRIFT_CORRECT_ACCUM'
        move_delay[nm] = dev_base[nm]+'MOV_TIME_DLY'
        script_loop_time[nm] = dev_base[nm]+'LOOP_TIME'
        use_drift_correction[nm] = self.locker_config['use_drift_correction']
        use_dither[nm] = self.locker_config['use_dither']
        dither_level[nm] = dev_base[nm]+'DITHER'
        bucket_correction_delay[nm] = str(self.locker_config['bucket_correction_delay'])
        
        while not (self.name in namelist):
            print(self.name + '  not found, please enter one of the following: ')
            for x in namelist:
                print(x)
            self.name = input('Enter system name:')                           

        self.use_drift_correction = use_drift_correction[self.name] # Turns drift correction on/off based on which laser locker is selected
        if self.use_drift_correction:
            self.drift_correction_dir = drift_correction_dir[self.name] # Sets drift correction direction based on which laser locker is selected
        self.use_dither = use_dither[self.name] # Used to allow fast dither of timing
        if self.use_dither:
            self.dither_level = dither_level[self.name]                  

        # List of other PVs used.
        self.pvlist['watchdog'] =  Pv(dev_base[self.name]+'FS_WATCHDOG')
        self.pvlist['oscillator_f'] =  Pv(dev_base[self.name]+'FS_OSC_TGT_FREQ')
        self.pvlist['time'] =  Pv(dev_base[self.name]+'FS_TGT_TIME')
        self.pvlist['time_hihi'] =  Pv(dev_base[self.name]+'FS_TGT_TIME.HIHI')
        self.pvlist['time_lolo'] =  Pv(dev_base[self.name]+'FS_TGT_TIME.LOLO')
        self.pvlist['calibrate'] =  Pv(dev_base[self.name]+'FS_START_CALIB')
        self.pvlist['enable'] =  Pv(dev_base[self.name]+'FS_ENABLE_TIME_CTRL')
        self.pvlist['busy'] =  Pv(dev_base[self.name]+'FS_CTRL_BUSY')
        self.pvlist['error'] =  Pv(dev_base[self.name]+'FS_TIMING_ERROR')
        self.pvlist['ok'] =  Pv(dev_base[self.name]+'FS_LASER_OK')
        self.pvlist['fix_bucket'] =  Pv(dev_base[self.name]+'FS_ENABLE_BUCKET_FIX')   
        self.pvlist['delay'] =  Pv(dev_base[self.name]+'FS_TRIGGER_DELAY')
        self.pvlist['offset'] =  Pv(dev_base[self.name]+'FS_TIMING_OFFSET')
        self.pvlist['enable_trig'] =  Pv(dev_base[self.name]+'FS_ENABLE_TRIGGER')
        self.pvlist['bucket_error'] =  Pv(dev_base[self.name]+'FS_BUCKET_ERROR')
        self.pvlist['bucket_counter'] =  Pv(dev_base[self.name]+'FS_CORRECTION_CNT')
        self.pvlist['deg_Sband'] =  Pv(dev_base[self.name]+'PDES')
        self.pvlist['deg_offset'] =  Pv(dev_base[self.name]+'POC')
        self.pvlist['ns_offset'] =  Pv(dev_base[self.name]+'FS_NS_OFFSET')
        self.pvlist['calib_error'] =  Pv(dev_base[self.name]+'FS_CALIB_ERROR')
        self.pvlist['counter'] = Pv(counter_base[self.name]+'GetOffsetInvMeasMean')  #time interval counter result, create PV
        self.pvlist['counter_low'] = Pv(counter_base[self.name]+'GetOffsetInvMeasMean.LOW')        
        self.pvlist['counter_high'] = Pv(counter_base[self.name]+'GetOffsetInvMeasMean.HIGH')        
        self.pvlist['counter_jitter'] = Pv(counter_base[self.name]+'GetMeasJitter')
        self.pvlist['counter_jitter_high'] = Pv(counter_base[self.name]+'GetMeasJitter.HIGH')        
        self.pvlist['freq_counter'] = Pv(freq_counter[self.name])  # frequency counter readback        
        self.pvlist['phase_motor'] = Pv(phase_motor[self.name])  # phase control smart motor
        self.pvlist['phase_motor_dmov'] = Pv(phase_motor[self.name]+'.DMOV')  # motor motion status
        self.pvlist['phase_motor_rb'] = Pv(phase_motor[self.name]+'.RBV')  # motor readback
        self.pvlist['freq_sp'] =  Pv(dev_base[self.name]+'FREQ_SP')  # frequency counter setpoint
        self.pvlist['freq_err'] = Pv(dev_base[self.name]+'FREQ_ERR') # frequency counter error
        self.pvlist['rf_pwr']= Pv(dev_base[self.name]+'CH1_RF_PWR') # RF power readback
        self.pvlist['rf_pwr_lolo']= Pv(dev_base[self.name]+'CH1_RF_PWR'+'.LOLO') # RF power readback
        self.pvlist['rf_pwr_hihi']= Pv(dev_base[self.name]+'CH1_RF_PWR'+'.HIHI') # RF power readback 
        self.pvlist['diode_pwr'] = Pv(dev_base[self.name]+'CH1_DIODE_PWR')
        self.pvlist['diode_pwr_lolo'] = Pv(dev_base[self.name]+'CH1_DIODE_PWR'+'.LOLO')
        self.pvlist['diode_pwr_hihi'] = Pv(dev_base[self.name]+'CH1_DIODE_PWR'+'.HIHI')
        self.pvlist['laser_trigger'] = Pv(laser_trigger[self.name])
        self.pvlist['laser_locked'] = Pv(dev_base[self.name]+'PHASE_LOCKED')
        self.pvlist['lock_enable'] = Pv(dev_base[self.name]+'RF_LOCK_ENABLE')
        self.pvlist['unfixed_error'] =  Pv(dev_base[self.name]+'FS_UNFIXED_ERROR')
        self.pvlist['bucket_correction_delay'] = Pv(bucket_correction_delay[self.name])
        self.pvlist['move_time_delay'] = Pv(move_delay[self.name]) # Delay between when set time is changed and when counter readback changes
        self.pvlist['loop_time'] = Pv(script_loop_time[self.name]) # Run time of the main program loop 
        if self.use_drift_correction:
            self.pvlist['drift_correction_signal'] = Pv(drift_correction_signal[self.name])
            self.pvlist['drift_correction_value'] = Pv(drift_correction_value[self.name])
            self.pvlist['drift_correction_offset'] = Pv(drift_correction_offset[self.name])
            self.pvlist['drift_correction_gain'] =  Pv(drift_correction_gain[self.name])
            self.pvlist['drift_correction_smoothing'] =  Pv(drift_correction_smoothing[self.name])
            self.pvlist['drift_correction_accum'] = Pv(drift_correction_accum[self.name])
        if self.use_dither:
            self.pvlist['dither_level'] = Pv(dither_level[self.name]) 
        self.OK = 1
        for k, v in self.pvlist.items():  # Now loop over all pvs to initialize
            try:
                v.get(ctrl=True, timeout=1.0) # Get data
            except: 
                print('Could not open:', v.name, '(', k, '),', 'Error occurred at:', date_time())
                logging.warning('Could not open: %s (%s), Error occurred at: %s', v.name, k, date_time())
                self.OK = 0 # Error with setting up PVs, can't run, will exit  
        self.error_pv = Pv(error_pv_name[self.name]) # Open pv
        self.version_pv = Pv(version_pv_name[self.name])
        self.version_pv.put(self.version, timeout = 10.0)
        self.E = error_output(self.error_pv)
        self.E.write_error('OK')

    def get(self, name):
        """Takes a PV name, connects to it, and returns its value."""
        if self.err_idx == 0: # Start of a new PV error report cycle
            self.report_start = time.time() # Start time of PV error report
        try:
            self.pvlist[name].get(ctrl=True, timeout=10.0)
            return self.pvlist[name].value                      
        except:
            self.PV_errs[self.err_idx] = str(name)+' - read' # Store PV name that caused error 
            self.err_idx += 1 # Increase PV error counter
            return 0 
        finally:
            self.PV_err_report()
  
    def get_last(self, name):
        """Takes a PV name and returns its last value, without connecting to the PV."""
        return self.pvlist[name].value                
                
    def put(self, name, x):
        """Takes a PV name, connects to it, and then writes a value to it."""
        if self.err_idx == 0: # Start of a new PV error report cycle
            self.report_start = time.time() # Start time of PV error report
        try:
            self.pvlist[name].put(x, timeout = 10.0) # long timeout           
        except:
            self.PV_errs[self.err_idx] = str(name)+' - write' # Store PV name that caused error 
            self.err_idx += 1 # Increase PV error counter
        finally:
            self.PV_err_report()
                
    def PV_err_report(self):
        self.curr_time = time.time()
        self.diff = self.curr_time - self.report_start # Compare current time to time at start of report
        try:
            if self.diff >= 600: # Have we reached 10 minutes?
                self.num_errs = len(self.PV_errs) # Total number of errors that have occurred
                self.PV_err_list = self.PV_errs.values()
                if self.num_errs >= 1: # If an error has occurred, print report
                    print('Current time:', date_time(), 'In the past 10 minutes,', self.num_errs, 'PV connection errors have occurred.')
                    logging.warning('In the past 10 minutes, %s PV connection errors have occurred.', self.num_errs)
                    print('Error report: ')
                    logging.warning('Error report: ')
                    self.PV_err_short = set(self.PV_err_list) # List each PV only once
                    for n in self.PV_err_short: # Loop over all unique PV errors
                        self.report_num = self.PV_err_list.count(n) # Calculate the number of times current PV error occurred
                        print('PV Name/Error Type:', n, 'Connection Errors:', self.report_num)
                        logging.warning('PV Name/Error Type: %s Connection Errors: %s', n, self.report_num)
                self.err_idx = 0 # Restart PV error counter regardless of whether error has occurred
        except:
            self.err_idx = 0 #If loop breaks, restart the counter so we don't spam the log
            return

    def __del__ (self):
        """Disconnects from all IOC PVs."""
        for v in self.pvlist.values():
            v.disconnect()  
        self.error_pv.disconnect()    
        print('Closed all PV connections at', date_time())
        logging.warning('Closed all PV connections.')


class locker():
    """Sets up locker parameters, performs calibrations, sets laser time, and corrects for bucket jumps."""
    def __init__(self, P, W):
         """Takes locker PVs and Watchdog and assigns laser locker specific values to variables."""
         self.P = P
         self.W = W  # watchdog class
         self.laser_f = 0.068 # 68MHz laser frequency
         self.locking_f = 3.808 # 3.808GHz locking frequency 
         self.trigger_f = 0.119 # 119MHz trigger frequency
         self.calib_points = 50  # number of points to use in calibration cycle
         self.calib_range = 30  # ns for calibration sweep
         self.max_jump_error = .05 # ns threshold for determing if counter is stable enough for bucket correction
         self.instability_thresh = 0.5 # ns threshold for "Counter not stable" message
         self.max_frequency_error = 100.0
         self.min_time = -880000 # minimum time that can be set (ns) % was 100  %%%% tset
         self.max_time = 20000.0 # maximum time that can be set (ns)
         self.d = dict()
         self.d['delay'] =  self.P.get('delay')
         self.d['offset'] = self.P.get('offset')
         self.delay_offset = 0  # kludge to avoide running near sawtooth edge
         self.drift_last= 0; # used for drift correction when activated
         self.drift_initialized = False # will be true after first cycle
         self.C = time_interval_counter(self.P) # creates a time interval counter object
         self.move_flag = 0
         self.bucket_flag = 0
         self.stale_cnt = 0 # Counter to determine if TIC is updating

    def locker_status(self):
        """Checks if core locker parameters are within optimal range and updates 'OK' flags accordingly."""
        self.laser_ok = 1 # list of various failure modes
        self.rf_ok = 1
        self.diode_ok = 1
        self.frequency_ok = 1
        self.setpoint_ok = 1
        self.lock_ok = 1
        self.message = 'OK' # output error message, OK means no trouble found    
        rfpwr = self.P.get('rf_pwr')  # check RF level
        rfpwrhihi = self.P.get('rf_pwr_hihi')
        rfpwrlolo = self.P.get('rf_pwr_lolo')
        if (rfpwr > rfpwrhihi) | (rfpwr < rfpwrlolo):
            self.message = 'RF power out of range'
            self.laser_ok = 0
            self.rf_ok = 0
        dpwr = self.P.get('diode_pwr') # check diode level
        dpwrhihi = self.P.get('diode_pwr_hihi')
        dpwrlolo = self.P.get('diode_pwr_lolo')
        if (dpwr > dpwrhihi) | (dpwr < dpwrlolo):
            self.message = 'Diode power out of range'
            self.laser_ok = 0
            self.rf_diode_ok = 0
        if abs(self.P.get('freq_sp') - self.P.get('oscillator_f')) > self.max_frequency_error:  # oscillator set point wrong
            self.laser_ok = 0
            self.frequency_ok = 0
            self.frequency_ok = 0
            self.message = 'Frequency set point out of range'
        if not self.P.get('laser_locked'):
            self.message = 'Laser not indicating lock'
            self.lock_ok = 0
            self.laser_ok = 0

    def calibrate(self):
        """Performs a linear sweep of phase motor range, sets the delay and offset values to minimize counter time error."""
        M = phase_motor(self.P)  # creates a phase motor control object (PVs were initialized earlier)
        T = trigger(self.P)  # trigger class
        ns = 10000 # number of different times to try for fit - INEFFICIENT - should do Newton's method but too lazy
        self.P.put('busy', 1) # set busy flag
        tctrl = np.linspace(0, self.calib_range, self.calib_points) # control values to use
        tout = np.array([]) # array to hold measured time data
        counter_good = np.array([]) # array to hold array of errors
        t_trig = T.get_ns() # trigger time in nanoseconds
        M.move(0)  # move to zero to start 
        M.wait_for_stop()
        for x in tctrl:  #loop over input array 
            self.W.check() # check watchdog
            if self.W.error:
                return    
            if not self.P.get('calibrate'):
                return   # canceled calibration
            M.move(x)  # move motor
            M.wait_for_stop()
            time.sleep(2)  #Don't know why this is needed
            t_tmp = 0 # to check if we ever get a good reading
            for n in range(0, 25): # try to see if we can get a good reading
                 t_tmp = self.C.get_time()  # read time
                 if t_tmp != 0: # have a new reading
                     break # break out of loop
            tout = np.append(tout, t_tmp) # read timing and put in array
            counter_good = np.append(counter_good, self.C.good) # will use to filter data
            if not self.C.good:
                print('Bad counter data. Occurred at:', date_time())
                logging.warning('Bad counter data.')
                self.P.E.write_error('Timer error, bad data - continuing to calibrate' ) # just for testing
        M.move(tctrl[0])  # return to original position    
        minv = min(tout[np.nonzero(counter_good)])+ self.delay_offset
        period = 1/self.laser_f # just defining things needed in sawtooth -  UGLY
        delay = minv - t_trig # More code cleanup needed in the future.
        err = np.array([]) # will hold array of errors
        offset = np.linspace(0, period, ns)  # array of offsets to try
        for x in offset:  # Tries different offsets to see what works
            S = sawtooth(tctrl, t_trig, delay, x, period) # Sawtooth simulation
            err = np.append(err, sum(counter_good*S.r * (S.t - tout)**2))  # Total error
        idx = np.argmin(err) # Index of minimum error
        S = sawtooth(tctrl, t_trig, delay, offset[idx], period)
        self.P.put('calib_error', np.sqrt(err[idx]/ self.calib_points))
        self.d['delay'] = delay
        self.d['offset'] = offset[idx]
        self.P.put('delay', delay)
        self.P.put('offset', offset[idx])
        M.wait_for_stop() # wait for motor to stop moving before exit
        self.P.put('busy', 0)        
        
    def set_time(self):
        """Takes user-entered target time and sets trigger time and phase motor position accordingly."""
        t = self.P.get('time')
        if math.isnan(t):
            self.P.E.write_error('desired time is NaN')
            return
        if t < self.min_time or t > self.max_time:
            self.P.E.write_error('need to move TIC trigger')
            return
        t_high = self.P.get('time_hihi')
        t_low = self.P.get('time_lolo')
        if t > t_high:
            t = t_high
            self.P.E.write_error('TGT bigger than time_hihi')
        if t < t_low:
            t = t_low
            self.P.E.write_error('TGT smaller than time_lolo')
        T = trigger(self.P) # set up trigger
        M = phase_motor(self.P)
        laser_t = t - self.d['offset']  # Apply offset to trigger time
        nlaser = np.floor(laser_t * self.laser_f) 
        pc = t - (self.d['offset'] + nlaser / self.laser_f) 
        pc = np.mod(pc, 1/self.laser_f)
        ntrig = round((t - self.d['delay'] - (1/self.trigger_f)) * self.trigger_f) # paren was after laser_f
        trig = ntrig / self.trigger_f
        if self.P.use_drift_correction:
            dc = self.P.get('drift_correction_signal') / 1000; # readback is in ps, but drift correction is ns, need to convert
            do = self.P.get('drift_correction_offset') 
            dg = self.P.get('drift_correction_gain')
            dd = self.P.drift_correction_dir
            ds = self.P.get('drift_correction_smoothing')
            self.drift_last = self.P.get('drift_correction_value')
            accum = self.P.get('drift_correction_accum')
            # modified to not use drift_correction_offset or drift_correction_multiplier:
            de = (dc-do)  # (hopefully) fresh pix value from TT script
            if ( self.drift_initialized ):
                if ( dc != self.dc_last ):           
                    if ( accum == 1 ): # if drift correction accumulation is enabled
                        #TODO: Pull these limits from the associated PV
                        self.drift_last = self.drift_last + (de- self.drift_last) / ds; # smoothing
                        self.drift_last = max(-.001, self.drift_last) # floor at 1 ps
                        self.drift_last = min(.001, self.drift_last)#
                        self.P.put('drift_correction_value', self.drift_last)
                        self.dc_last = dc
            else:
                self.drift_last = de # initialize to most recent reading
                self.drift_last = max(-.001, self.drift_last) # floor at 1 ps
                self.drift_last = min(.001, self.drift_last)#
                self.dc_last = dc
                self.drift_initialized = True # will average next time (ugly)    
            pc = pc - (dd * dg * self.drift_last); # fix phase control. 
        if self.P.use_dither:
            dx = self.P.get('dither_level') 
            pc = pc + (random.random()-0.5)* dx / 1000 # uniformly distributed random. 

        if self.P.get('enable_trig'): # Full routine when trigger can move
            if T.get_ns() != trig:   # need to move
                T.set_ns(trig) # sets the trigger
        self.pc_diff = M.get_position() - pc  # difference between current phase motor and desired time        
        if abs(self.pc_diff) > 1e-6:
            M.move(pc) # moves the phase motor
            self.move_start = time.time() # Time that set time was changed - used by the move_time_delay() function.
            self.pc_out = pc # For move time delay function 
      
    def check_jump(self):
        """Takes the trigger time, phase motor position, and counter time, calculates the number of 3.808 GHz bucket jumps."""
        T = trigger(self.P) # trigger class
        M = phase_motor(self.P) # phase motor     
        t = self.C.get_time()
        if t > -900000.0:      
            self.P.put('error', t - self.P.get('time')) # timing error (reads counter)      
        t_trig = T.get_ns()
        pc = M.get_position()
        try:
            self.d['delay'] = self.P.get('delay')
            self.d['offset'] = self.P.get('offset')
        except:
            print('Problem reading delay and offset pvs. Error occurred at:', date_time())
            logging.error('Problem reading delay and offset pvs.')
        S = sawtooth(pc, t_trig, self.d['delay'], self.d['offset'], 1/self.laser_f) # calculate time        
        self.terror = t - S.t # error in ns
        self.buckets = round(self.terror * self.locking_f)
        self.bucket_error = self.terror - self.buckets / self.locking_f
        self.exact_error = self.buckets / self.locking_f  # number of ns to move (exactly)
        if (self.C.range > self.C.tol):
            self.P.E.write_error('Counter not stable')
        if (self.C.range == 0) and (self.C.range < self.C.tol):  # No TIC reading
            if (self.stale_cnt < 500):
                self.stale_cnt += 1
                print(self.stale_cnt) #For troubleshooting purposes only
            else:
                self.stale_cnt = 0
                self.P.E.write_error('No counter reading')
        else:
            self.stale_cnt = 0 # Reset the stale counter if there is new TIC data
        if (self.C.range > (2 * self.max_jump_error)) or (self.C.range == 0): # Too wide a range of measurements
            self.buckets = 0  # Do not count as a bucket error if readings are not consistent
            return
        if abs(self.bucket_error) > self.max_jump_error:
            self.buckets = 0
            self.P.E.write_error('Not an integer number of buckets')
        if self.buckets != 0:
            self.detection_t = time.time() # Time bucket jump was detected
        self.P.E.write_error('Laser OK') # Laser is OK
            
    def fix_jump(self):
        """Takes exact bucket error is ns, moves the phase motor and updates the offset to correct for it."""
        if self.buckets == 0:  #no jump to begin with
            self.P.E.write_error('Trying to fix non-existent jump')
            return
        if abs(self.bucket_error) > self.max_jump_error:
            self.P.E.write_error( 'Non-integer bucket error, cant fix')
            return
        self.P.E.write_error( 'Fixing Jump')
        M = phase_motor(self.P) #phase control motor
        M.wait_for_stop()  # just to be sure
        old_pc = M.get_position()
        new_pc = old_pc  - self.exact_error # new time for phase control
        new_pc_fix = np.mod(new_pc, 1/self.laser_f)  # equal within one cycle. 
        M.move(new_pc_fix) # moves phase motor to new position
        M.wait_for_stop()
        time.sleep(2)
        new_offset = self.d['offset'] - (new_pc_fix - old_pc)
        self.d['offset'] = new_offset
        self.P.put('offset', new_offset)
        self.P.E.write_error('Done Fixing Jump')
        bc = self.P.get('bucket_counter') # previous number of jumps
        self.P.put('bucket_counter', bc + 1)  # write incremented number

    def move_time_delay(self):
        """Takes the time of the most recent set time adjustment, returns the approximate delay that occurred before the time interval counter detected the change in time."""
        try:
            if abs(self.pc_diff) > 1e-6 or self.move_flag == 1: # Checks if phase motor set position has changed
                self.curr_time = self.C.get_time() # Current counter time
                T = trigger(self.P)
                t_trig = T.get_ns()
                S = sawtooth(self.pc_out, t_trig, self.P.get('delay'), self.P.get('offset'), 1/self.laser_f) # Calculate theoretical laser time 
                if abs(self.curr_time - S.t) < 0.25: # Checks if counter reading is within 250 ps of set time
                    move_stop = time.time() # Time of change in counter time
                    move_delay = move_stop - self.move_start # Calculates approximate time in seconds it took to make see change in time on counter. Imprecise because femto.py loop delay.
                    self.P.put('move_time_delay', move_delay)
                    self.move_flag = 0
                else:
                    self.move_flag = 1
            if self.buckets != 0 or self.bucket_flag == 1:
                self.curr_time = self.C.get_time() # Current counter time
                T = trigger(self.P)
                t_trig = T.get_ns()
                S = sawtooth(self.pc_out, t_trig, self.P.get('delay'), self.P.get('offset'), 1/self.laser_f) # Calculate theoretical laser time 
                if abs(self.curr_time - S.t) < 0.25: # Checks if counter reading is within 250 ps of set time
                    self.correction_t = time.time() # Time of change in counter time
                    self.corr_diff = self.correction_t - self.move_start # Calculates approximate time in seconds it took to make see change in time on counter due to bucket correction. Imprecise because femto.py loop delay.
                    self.P.put('bucket_correction_delay', self.corr_diff)
                    self.bucket_flag = 0
                else:
                    self.bucket_flag = 1
        except AttributeError as a:
            print('Attribute error in move_time_delay:', a)
            logging.error('Attribute error in move_time_delay: %s', a)
        except TypeError as t:
            print('Type error in move_time_delay', t)
            logging.error('Type error in move_time_delay %s', t)
       
            
class sawtooth():
    """Takes phase motor position, EVR trigger time, delay, offset, and the Vitara period, and calculates the net laser time."""
    def __init__(self, t0, t_trig, delay, offset, period):
        trig_out = t_trig + delay # t_trig is the EVR trigger time, delay is the cable length after the trigger
        laser_t0 = t0 + offset # t0 is an array of inputs that represent the phase shift time, offset is the delay from the photodiode to the time interval counter
        tx = trig_out - laser_t0
        nlaser = np.ceil(tx / period)
        self.t = t0 + offset + nlaser * period
        tr = self.t - trig_out
        self.r = (0.5 + np.copysign(.5, tr - 0.2 * period)) * (0.5 + np.copysign(.5, .8 * period - tr)) # no sign function


class ring():
    """A twelve element ring buffer."""
    def __init__(self, sz=12):
        """Takes a size value, creates an array for the ring buffer."""
        self.sz = sz  # hold size of ring
        self.a = np.zeros(sz)
        self.ptr = -1 # points to last data, start negative
        self.full = False # set to true when the ring is full
        
    def add_element(self, x):
        """Takes an element index, adds an element to the ring at that index."""
        self.ptr = np.mod(self.ptr+1,self.sz)        
        self.a[self.ptr] = x # set this element
        if self.ptr == 7:
            self.full = True

    def get_last_element(self):
        """Returns most recently added element of the buffer."""
        return self.a[self.ptr]       
        
    def get_array(self):
        """Returns entire ring buffer array."""
        return self.a
        
 
class time_interval_counter():
    """Returns SR620 counter time if it is in acceptable range and jitter is acceptably low."""
    def __init__(self, P):
        """Takes counter PVs, creates ring buffer for counter data."""
        self.scale = 1e9 # scale relative to nanoseconds
        self.P = P
        self.good = 1 
        self.rt = ring() # create a ring buffer to hold data
        self.rt.add_element(self.P.get('counter')) # read first counter value to initialize array
        self.rj = ring() # ring to hold jitter data
        self.rj.add_element(self.P.get('counter_jitter'))
        self.range = 0 # range of data

    def get_time(self):
        """Returns counter time scaled to ns."""
        self.good = 0  # assume bad unless we fall through all the traps
        self.range = 0; # Until overwritten by new data
        self.tol = self.P.get('counter_jitter_high')
        tmin = self.P.get('counter_low')
        tmax = self.P.get('counter_high')
        time = self.P.get('counter')  # read counter time
        if time == self.rt.get_last_element: # no new data
            return 0 # no new data
        if (time > tmax) or (time < tmin):
            return 0 # data out of range
        jit = self.P.get('counter_jitter')
        if jit > self.tol:
            return 1  # 1 to differentiate from no data or out of range data
        # if we got here, we have a good reading
        self.rt.add_element(time) # add time to ring
        self.rj.add_element(jit)  # add jitter to ring
        self.good = 1
        if self.rt.full:
            self.range = self.scale * (max(self.rt.get_array()) - min(self.rt.get_array()))  # range of measurements
        return time * self.scale

   
class phase_motor():
    """Waits for phase motor to stop moving, reads and writes phase motor position."""
    def __init__(self, P):
        """Takes phase motor PVs, sets up phase motor movement parameters."""
        self.scale = .001 # motor is in ps, everthing else in ns
        self.P = P
        self.max_tries = 100
        self.loop_delay = 0.1
        self.tolerance = 3e-5  #was 5e-6 #was 2e-5
        self.position = self.P.get('phase_motor') * self.scale  # get the current position  WARNING logic race potential
        self.wait_for_stop()  # wait until it stops moving

    def wait_for_stop(self):
        """Sleeps until phase motor is stopped and within tolerance of set value."""
        for n in range(0, self.max_tries):
            try:
                stopped = self.P.get('phase_motor_dmov') # 1 if stopped, if throws error, is still moving
            except:
                print('Could not get dmov. Error occurred at:', date_time())
                logging.error('Could not get dmov.')
                stopped = 0  # threw error, assume not stopped (should clean up to look for epics error)
            if stopped:
                posrb = self.P.get('phase_motor_rb') * self.scale  # position in nanoseconds
                if abs(posrb - self.position) < self.tolerance:  # are we within range
                   break
            time.sleep(self.loop_delay)        

    def move(self, pos):
        """Takes target position, moves phase motor to target value in ps."""
        self.P.put('phase_motor', pos/self.scale) # motor move if needed   
        self.position = pos  # requested position in ns
        self.wait_for_stop() # check
         
    def get_position(self):
        """Returns phase motor position in ns."""
        self.wait_for_stop() # wait until it stops moving
        self.position = self.scale * self.P.get('phase_motor')  # get position data
        return self.position           


class trigger():
    """Reads and writes EVR trigger delay in ns."""
    def __init__ (self, P):  # Takes trigger scaling information from PV list
        self.P = P
        self.time = self.P.get('laser_trigger')    
   
    def get_ns(self):
        """Takes trigger PV, returns current trigger time in ns."""
        tmp = self.P.get('laser_trigger')
        self.time = tmp
        return self.time
        
    def set_ns(self,t):
        """Sets trigger time in ns."""
        self.time = t
        self.P.put('laser_trigger', self.time)
   
  
class error_output():
    """Writes error messages to a PV."""
    def __init__(self, pv):
        """Takes error PV, sets it to default OK state."""
        self.pv = pv
        self.pv.put(value= 'OK', timeout=1.0) #Error message default is 'OK'
        self.maxlen = 25 # Maximum error string length
  
    def write_error(self, txt):
        """Takes error string text, writes it to error PV."""
        n = len(txt)
        if n > self.maxlen:
            txt = txt[0:self.maxlen]
        self.pv.put(value = txt, timeout = 1.0)


class degrees_s():
    """Ensures the current time and degrees values match one another."""
    def __init__(self, P):
        """Takes degrees and time PVs, sets up parameters for conversion to degrees."""
        self.P = P # P is the list of PVs
        self.freq = 2.856  # in GHz
        self.last_time = self.P.get('time') # last time entered in contol
        self.last_deg = self.P.get('deg_Sband') # last degrees sband
        self.last_ns_offset = self.P.get('ns_offset')
        self.last_deg_offset = self.P.get('deg_offset')
        
    def run(self):
        """Takes degrees and ns time values, updates them to match one another. ns time value is given priority if they have both changed."""
        ns = self.P.get('time')
        deg = self.P.get('deg_Sband')
        ns_offset = self.P.get('ns_offset')
        deg_offset = self.P.get('deg_offset')
        if ns != self.last_time or ns_offset != self.last_ns_offset: # nanoseconds have changed
           deg_new = -1.0*(ns - ns_offset) * self.freq * 360 - deg_offset
           self.last_time = ns
           self.last_ns_offset = ns_offset
           self.last_deg = deg_new
           self.P.put('deg_Sband', deg_new) #write the degrees back
           
        elif deg != self.last_deg or deg_offset != self.last_deg_offset:  #changed degrees
           ns_new = -1.0*(deg + deg_offset)/(self.freq * 360) + ns_offset
           self.last_time = ns_new
           self.last_deg = deg
           self.last_deg_offset = deg_offset
           self.P.put('time', ns_new) 

        else:
            pass        


def date_time():
    """Returns the current date and time."""
    loc_time = time.localtime()
    curr_time = time.asctime(loc_time)
    return curr_time


def femto(name='NULL'):
    """Takes name of locking system, performs complete locking and timing routine."""
    P = PVS(name)
    if P.OK == 0:
        return
    W = watchdog.watchdog(P.pvlist['watchdog'])
    if W.error:
        return
    L = locker(P,W) # Sets up locking system parameters
    L.locker_status()  # Checks locking system / laser status
    P.E.write_error(L.message)
    T = trigger(P)
    T.get_ns()
    D = degrees_s(P) # Enables degrees to be converted to ns, and vice versa
    while W.error == 0:   # MAIN PROGRAM LOOP
        time.sleep(0.1)
        try:   
            loop_start = time.time()
            W.check()
            P.put('busy', 0)
            L.locker_status()  # Checks if the locking system is OK
            if not L.laser_ok:  # If the laser is not in OK state, report error and try again
                P.E.write_error(L.message)
                P.put('ok', 0)
                time.sleep(0.5)  # Keeps the loop from spinning too fast
                continue        
            if P.get('calibrate'): # Executed if a calibration is requested
                P.put('ok', 0)
                P.put('busy', 1) # Sets busy flag while calibrating
                P.E.write_error( 'calibration requested - starting')
                L.calibrate()
                P.put('calibrate', 0)
                P.E.write_error( ' calibration done')
                continue
            L.check_jump()   # Checks for bucket jumps
            if P.get('fix_bucket') and L.buckets != 0 and P.get('enable'):
                P.put('ok', 0)
                P.put('busy', 1)
                L.fix_jump()  # Fixes bucket jumps
            P.put('bucket_error',  L.buckets)
            P.put('unfixed_error', L.bucket_error)
            P.put('ok', 1)
            if P.get('enable'): # Checks if time control is enabled
                L.set_time() # Sets laser time
                L.move_time_delay() # Record delay between set time change and change in counter readback
            D.run()  # Ensures degrees and ns time value match
            loop_stop = time.time()
            loop_time = loop_stop - loop_start
            P.put('loop_time', loop_time)
        except:   # Catch any otherwise uncaught error.
            print(sys.exc_info()[0]) # Print error
            logging.error('%s', sys.exc_info()[0])
            del P  #does this work?
            print('UNKNOWN ERROR, trying again. Error occurred at:', date_time())
            P = PVS(name)
            W = watchdog.watchdog(P.pvlist['watchdog'])
            L = locker(P, W) #set up locking system parameters
            L.locker_status()  # check locking system / laser status
            P.E.write_error(L.message)
            T = trigger(P)
            T.get_ns()
    P.E.write_error( 'done, exiting')

if __name__ == "__main__":
    if len(sys.argv) < 2:
        femto()  # null input will prompt
    else:
        femto(sys.argv[1])
    
