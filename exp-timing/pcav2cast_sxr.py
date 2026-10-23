# Moves the SXR cable stabilizer (CAST) phase shifter to keep the RF phase aligned with the x-rays, using the phase cavity as the timing reference.
# Env: source /cds/group/pcds/pyps/conda/pcds_conda
#
# Controls (set these):
#   LAS:UNDS:FLOAT:05   Feedback enable      0 = off (report raw PCAV only, no PS writes)
#                                            1 = on
#   LAS:UNDS:FLOAT:95   PCAV source          0 = TIME0 (SXR beam)
#                                            1 = TIME1 (HXR / XPP beam)
#   LAS:UNDS:FLOAT:93   Loop gain
#   LAS:UNDS:FLOAT:94   Loop pause (s)
#   LAS:UNDS:FLOAT:50   Error jump threshold (ps); larger jumps skip that cycle
#   LAS:UNDS:FLOAT:92   PCAV (ps) -> phase shifter conversion
#
# Status (written by script):
#   LAS:UNDS:FLOAT:90   Heartbeat counter
#   LAS:UNDS:FLOAT:06   Averaged timing error (ps)
#   LAS:UNDS:FLOAT:51   Last correction sent to phase shifter
#   LAS:UNDS:FLOAT:91   Loop status code; .DESC holds the text:
#                         0 FB disabled         4 Latching setpoint
#                         1 Running             5 No valid setpoint
#                         2 Hold: error jump    6 PCAV NaN (a sample was NaN)
#                         3 Hold: stale PCAV
#
# Hardware:
#   SIOC:UNDS:PT01:0:TIME0   Phase cavity, SXR beam
#   SIOC:UNDS:PT01:0:TIME1   Phase cavity, HXR beam
#   LAS:UND:MMS:01           NEH CAST phase shifter (PS)
import time
import datetime
import epics
import numpy as np

######################################
# SXR PV definition
######################################
HB_PV = 'LAS:UNDS:FLOAT:90'
SXR_FB_PV = 'LAS:UNDS:FLOAT:05'
STATUS_PV = 'LAS:UNDS:FLOAT:91'
STATUS_DESC_PV = STATUS_PV + '.DESC'
SXR_GAIN_PV = 'LAS:UNDS:FLOAT:92'
SXR_LOOP_GAIN_PV = 'LAS:UNDS:FLOAT:93'
SXR_LOOP_PAUSE_PV = 'LAS:UNDS:FLOAT:94'
SXR_PCAV_PV0 = 'SIOC:UNDS:PT01:0:TIME0'
SXR_PCAV_PV1 = 'SIOC:UNDS:PT01:0:TIME1'
SXR_PCAV_AVG_PV = 'LAS:UNDS:FLOAT:06'
SXR_CAST_PS_PV_W = 'LAS:UND:MMS:01'
SXR_CAST_PS_PV_R = SXR_CAST_PS_PV_W + '.RBV'    # Phase shifter PV readback
SXR_THRESH_PV = 'LAS:UNDS:FLOAT:50'
SXR_CTRL_DELTA_PV = 'LAS:UNDS:FLOAT:51'

# init values
SXR_GAIN = 1.1283  # slope from plotting cast phase shifter v. PCAV value 
PAUSE_TIME = 5    # Let's give some time for the system to react
CTRL_OUT = epics.caget(SXR_CAST_PS_PV_R)    # initial value of the phase shifter
AVG_N = 5    # Taking 5 data samples to average and throw out outliers
LATCH_N = 15  # setpoint = median of 15 PCAV reads, 1 s apart (rejects bumps up to ~7 s)
# epics.caput(SXR_THRESH_PV, 1)  # set the error threshold to 1
SXR_FB_EN = epics.caget(SXR_FB_PV)
COUNTER = 0
epics.caput(HB_PV, COUNTER)
TIME_ERR_AVG_PREV = 0

# Setpoint the loop corrects to; latched (latch_setpoint) when feedback is enabled
CTRL_SETPT = None

time_err_ary = np.zeros((AVG_N,))
PCAV_temp_ary = np.zeros(2,)

# SXR specific for XPP
XPP_SWITCH_PV = 'LAS:UNDS:FLOAT:95'
# -1727400.6755412123

print('pcav2cast_sxr running test update 2026-10-22')

PREV_USE_PV1 = None
WAS_FB_ON = False


def ts():
    return datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')


def set_status(code, text):
    epics.caput(STATUS_PV, code)
    epics.caput(STATUS_DESC_PV, text)


def latch_setpoint(pv):
    vals = []
    for _ in range(LATCH_N):
        v = epics.caget(pv)
        if v is not None and not np.isnan(v):
            vals.append(v)
        time.sleep(1)
    return np.median(vals) if len(vals) > LATCH_N // 2 else None


# Main loop
while True:
    # FLOAT:05 = 0 -> only report the raw PCAV value, no setpoint, no PS writes.
    # On re-enable, latch a fresh setpoint and resume from the PS readback.
    FB_ON = bool(epics.caget(SXR_FB_PV))
    if FB_ON and not WAS_FB_ON:
        print(f'{ts()} | FB ENABLED')
    WAS_FB_ON = FB_ON

    # XPP switch 0 -> follow SXR beam (TIME0); nonzero -> follow HXR beam (TIME1).
    # Re-latch the setpoint on a switch so the new channel starts with ~0 error.
    USE_PV1 = bool(epics.caget(XPP_SWITCH_PV))
    PCAV_PV = SXR_PCAV_PV1 if USE_PV1 else SXR_PCAV_PV0
    src = 'TIME1 (HXR)' if USE_PV1 else 'TIME0 (SXR)'

    if not FB_ON:
        PREV_USE_PV1 = None  # forces a fresh latch when feedback is re-enabled
        set_status(0, 'FB disabled')
        print(f'{ts()} | FEEDBACK DISABLED | src={src} | pcav={epics.caget(PCAV_PV)}')
        COUNTER = COUNTER + 1
        epics.caput(HB_PV, COUNTER)
        time.sleep(epics.caget(SXR_LOOP_PAUSE_PV))
        continue

    if USE_PV1 != PREV_USE_PV1 or CTRL_SETPT is None:
        print(f'{ts()} | Latching setpoint from {PCAV_PV} ({LATCH_N} s)...')
        set_status(4, 'Latching setpoint')
        CTRL_SETPT = latch_setpoint(PCAV_PV)
        CTRL_OUT = epics.caget(SXR_CAST_PS_PV_R)
        TIME_ERR_AVG_PREV = 0
        PREV_USE_PV1 = USE_PV1
        print(f'{ts()} | setpoint latched: {CTRL_SETPT}, PS readback: {CTRL_OUT}')
        if CTRL_SETPT is None:
            print(f'{ts()} | HOLD: no valid setpoint, retrying')
            set_status(5, 'No valid setpoint')
            continue

    SXR_GAIN = epics.caget(SXR_GAIN_PV)
    PAUSE_TIME = epics.caget(SXR_LOOP_PAUSE_PV)
    LOOP_KP = epics.caget(SXR_LOOP_GAIN_PV)
    COUNTER = epics.caget(HB_PV)
    TIME_ERR_THRESH = epics.caget(SXR_THRESH_PV)  # error difference threshold

    NAN_ALERT = 0
    for h in range(0, AVG_N):
        PCAV_temp_ary[0,] = epics.caget(PCAV_PV)
        PCAV_temp_ary[1,] = epics.caget(PCAV_PV)
        PCAV_VAL = np.average(PCAV_temp_ary)
        if np.isnan(PCAV_VAL):
            PCAV_VAL = 0
            NAN_ALERT = 1
        time_err = np.around((CTRL_SETPT - PCAV_VAL), decimals=6)
        time_err_ary[h] = time_err
        time.sleep(0.1)

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
    # don't do feedback if the error is too large or the PCAV is stale
    STATUS = (1, 'Running')
    if (TIME_ERR_DIFF == 0) or (abs(TIME_ERR_DIFF) >= TIME_ERR_THRESH):
        CTRL_DELTA = 0
        STATUS = (3, 'Hold: stale PCAV') if TIME_ERR_DIFF == 0 else (2, 'Hold: error jump')
    if NAN_ALERT:
        CTRL_DELTA = 0
        STATUS = (6, 'PCAV NaN')
    set_status(*STATUS)
    CTRL_OUT = CTRL_OUT + CTRL_DELTA
    epics.caput(SXR_CTRL_DELTA_PV, CTRL_DELTA)
    print(f'{ts()} | RUNNING | src={src} | {STATUS[1]} | err={TIME_ERR_AVG} delta={CTRL_DELTA} out={CTRL_OUT}')
    epics.caput(SXR_CAST_PS_PV_W, CTRL_OUT)
    TIME_ERR_AVG_PREV = TIME_ERR_AVG
    COUNTER = COUNTER + 1
    epics.caput(HB_PV, COUNTER)
    time.sleep(PAUSE_TIME)
