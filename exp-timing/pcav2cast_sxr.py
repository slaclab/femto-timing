# Moves the SXR cable stabilizer (CAST) phase shifter to keep the RF phase aligned with the x-rays, using the phase cavity as the timing reference.
# Env: source /cds/group/pcds/pyps/conda/pcds_conda
import time
import datetime
import epics
import numpy as np

######################################
# SXR PV definition
######################################
HB_PV = 'LAS:UNDS:FLOAT:90'  # Heartbeat PV
SXR_FB_PV = 'LAS:UNDS:FLOAT:05'  # Feedback enable PV
SXR_NAN_PV = 'LAS:UNDS:FLOAT:91'    # NAN alert PV
SXR_NAN_PVDESC = SXR_NAN_PV + '.DESC'   # NAN alert PV description
SXR_GAIN_PV = 'LAS:UNDS:FLOAT:92'   # conversion factor from pcav to cast
SXR_LOOP_GAIN_PV = 'LAS:UNDS:FLOAT:93'  # Loop gain PV
SXR_LOOP_PAUSE_PV = 'LAS:UNDS:FLOAT:94' # Loop pause time PV
SXR_PCAV_PV0 = 'SIOC:UNDS:PT01:0:TIME0' # Phase cavity PV0 (SXR)
SXR_PCAV_PV1 = 'SIOC:UNDS:PT01:0:TIME1' # Phase cavity PV1 (HXR)
SXR_PCAV_AVG_PV = 'LAS:UNDS:FLOAT:06'   # Phase cavity average PV
SXR_CAST_PS_PV_W = 'LAS:UND:MMS:01' # Phase shifter PV write
SXR_CAST_PS_PV_R = SXR_CAST_PS_PV_W + '.RBV'    # Phase shifter PV readback
SXR_THRESH_PV = 'LAS:UNDS:FLOAT:50'    # error threshold PV
SXR_CTRL_DELTA_PV = 'LAS:UNDS:FLOAT:51'  # error difference PV

# init values
SXR_GAIN = 1.1283  # slope from plotting cast phase shifter v. PCAV value 
PAUSE_TIME = 5    # Let's give some time for the system to react
CTRL_OUT = epics.caget(SXR_CAST_PS_PV_R)    # initial value of the phase shifter
AVG_N = 5    # Taking 5 data samples to average and throw out outliers
# epics.caput(SXR_THRESH_PV, 1)  # set the error threshold to 1
SXR_FB_EN = epics.caget(SXR_FB_PV)
COUNTER = 0
epics.caput(HB_PV, COUNTER)
TIME_ERR_AVG_PREV = 0
epics.caput(SXR_NAN_PV, 0)
epics.caput(SXR_NAN_PVDESC, 'No NaN read')
NAN_ALERT = 0

# We are doing an exponential fb loop, where the output = output[-1] + (-gain * error)
# Latch in the value before starting the feedback, this will be value we correct to
CTRL_SETPT = epics.caget(SXR_PCAV_PV1)

time_err_ary = np.zeros((AVG_N,))
PCAV_temp_ary = np.zeros(2,)

# SXR specific for XPP
XPP_SWITCH_PV = 'LAS:UNDS:FLOAT:95'  # 0 = PCAV TIME1 (HXR beam), nonzero = TIME0 (SXR beam)
SCRIPT_EN_PV = 'LAS:UNDS:FLOAT:96'  # 0 = idle (no PS writes), nonzero = script active
# -1727400.6755412123

print('pcav2cast_sxr running test update 2026-10-22')

PREV_USE_PV0 = None
WAS_ENABLED = None  # None so the first state is always printed


def ts():
    return datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')


# Main loop
while True:
    if not bool(epics.caget(SCRIPT_EN_PV)):
        if WAS_ENABLED is not False:
            print(f'{ts()} | DISABLED ({SCRIPT_EN_PV} = 0) - idling, no PS writes')
        WAS_ENABLED = False
        COUNTER = COUNTER + 1
        epics.caput(HB_PV, COUNTER)  # stay visibly alive while idle
        time.sleep(1)
        continue
    if not WAS_ENABLED:
        # Resume from the phase shifter's current position with a fresh setpoint
        CTRL_OUT = epics.caget(SXR_CAST_PS_PV_R)
        print(f'{ts()} | ENABLED - resuming from PS readback {CTRL_OUT}')
        PREV_USE_PV0 = None
        WAS_ENABLED = True

    # XPP switch nonzero -> follow SXR beam (TIME0); 0 -> follow HXR beam (TIME1).
    # Re-latch the setpoint on a switch so the new channel starts with ~0 error.
    USE_PV0 = bool(epics.caget(XPP_SWITCH_PV))
    PCAV_PV = SXR_PCAV_PV0 if USE_PV0 else SXR_PCAV_PV1
    if USE_PV0 != PREV_USE_PV0:
        CTRL_SETPT = epics.caget(PCAV_PV)
        PREV_USE_PV0 = USE_PV0
        print(f'{ts()} | PCAV source: {PCAV_PV}, setpoint latched: {CTRL_SETPT}')

    SXR_GAIN = epics.caget(SXR_GAIN_PV)
    PAUSE_TIME = epics.caget(SXR_LOOP_PAUSE_PV)
    LOOP_KP = epics.caget(SXR_LOOP_GAIN_PV)
    COUNTER = epics.caget(HB_PV)
    TIME_ERR_THRESH = epics.caget(SXR_THRESH_PV)  # error difference threshold

    for h in range(0, AVG_N):
        PCAV_temp_ary[0,] = epics.caget(PCAV_PV)
        PCAV_temp_ary[1,] = epics.caget(PCAV_PV)
        PCAV_VAL = np.average(PCAV_temp_ary)
        if np.isnan(PCAV_VAL):
            PCAV_VAL = 0
            NAN_ALERT = 1
        else:
            NAN_ALERT = 0
        time_err = np.around((CTRL_SETPT - PCAV_VAL), decimals=6)
        time_err_ary[h] = time_err
        time.sleep(0.1)
    # Check for NaN values in the array
    if NAN_ALERT == 1:
        epics.caput(SXR_NAN_PV, NAN_ALERT)
        epics.caput(SXR_NAN_PVDESC, "NaN Detected")
    else:
        epics.caput(SXR_NAN_PV, NAN_ALERT)
        epics.caput(SXR_NAN_PVDESC, "No NaN")

    # Calculate the average error
    time_err_ary_sort = np.sort(time_err_ary)
    time_err_ary_sort1 = time_err_ary_sort[1:-1]  # remove the outliers
    TIME_ERR_AVG = np.mean(time_err_ary_sort1)
    epics.caput(SXR_PCAV_AVG_PV, TIME_ERR_AVG)

    if COUNTER == 0:
        TIME_ERR_DIFF = 0.01
    else:
        TIME_ERR_DIFF = TIME_ERR_AVG_PREV - TIME_ERR_AVG

    # apply the feedback control
    cntl_temp = np.multiply(TIME_ERR_AVG, SXR_GAIN)
    CTRL_DELTA = np.multiply(LOOP_KP, cntl_temp)
    SXR_FB_EN = epics.caget(SXR_FB_PV)  # get feedback enable PV
    # don't do feedback if the error is too large or feedback is disabled
    HOLD = 'FB active'
    if (TIME_ERR_DIFF == 0) or (abs(TIME_ERR_DIFF) >= TIME_ERR_THRESH) or (SXR_FB_EN == 0):
        CTRL_DELTA = 0
        HOLD = ('HOLD: FB disabled (FLOAT:05)' if SXR_FB_EN == 0 else
                'HOLD: stale PCAV' if TIME_ERR_DIFF == 0 else 'HOLD: error jump > thresh')
    CTRL_OUT = CTRL_OUT + CTRL_DELTA
    epics.caput(SXR_CTRL_DELTA_PV, CTRL_DELTA)
    src = 'TIME0 (SXR)' if USE_PV0 else 'TIME1 (HXR)'
    print(f'{ts()} | RUNNING | src={src} | {HOLD} | err={TIME_ERR_AVG} delta={CTRL_DELTA} out={CTRL_OUT}')
    epics.caput(SXR_CAST_PS_PV_W, CTRL_OUT)
    TIME_ERR_AVG_PREV = TIME_ERR_AVG
    COUNTER = COUNTER + 1
    epics.caput(HB_PV, COUNTER)
    time.sleep(PAUSE_TIME)
