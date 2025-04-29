#####################################################################
# Filename: pcav2cast_hxr.py
# Author: Chengcheng Xu (charliex@slac.stanford.edu)
#####################################################################
# This script will take the phase cavity value and put throw
# an exponential feedback controller, then output its value to the
# phase shifter in the cable stabilizer system
# To ensure right python env sourced
# source /reg/g/pcds/engineering_tools/xpp/scripts/pcds_conda
import epics as epics
import numpy as np
import time as time
import datetime

######################################
# HXR PV definition
######################################
HB_PV = 'LAS:UNDH:FLOAT:90'  # Heartbeat PV
HXR_FB_PV = 'LAS:UNDH:FLOAT:05'  # Feedback enable PV
HXR_NAN_PV = 'LAS:UNDH:FLOAT:91'    # NAN alert PV
HXR_NAN_PVDESC = HXR_NAN_PV + '.DESC'   # NAN alert PV description
HXR_GAIN_PV = 'LAS:UNDH:FLOAT:92'  # Gain PV
HXR_LOOP_GAIN_PV = 'LAS:UNDH:FLOAT:93'  # Loop gain PV
HXR_LOOP_PAUSE_PV = 'LAS:UNDH:FLOAT:94' # Loop pause time PV
HXR_PCAV_PV0 = 'SIOC:UNDH:PT01:0:TIME0' # Phase cavity PV0
HXR_PCAV_PV1 = 'SIOC:UNDH:PT01:0:TIME1' # Phase cavity PV1
HXR_PCAV_AVG_PV = 'LAS:UNDH:FLOAT:06'   # Phase cavity average PV
HXR_CAST_PS_PV_W = 'LAS:UND:MMS:02' # Phase shifter PV write
HXR_CAST_PS_PV_R = HXR_CAST_PS_PV_W + '.RBV'    # Phase shifter PV readback

# default initial values
HXR_GAIN = 2  # 03/1/2024 cal
PAUSE_TIME = 5    # Let's give some time for the system to react

# We are doing an exponential fb loop, where the output = output[-1] + (-gain * error)
pcavsp_ary = np.zeros(2,)
# Latch in the value before starting the feedback, this will be value we correct to
pcavsp_ary[0,] = epics.caget(HXR_PCAV_PV0)
# Latch in the value before starting the feedback, this will be value we correct to
pcavsp_ary[1,] = epics.caget(HXR_PCAV_PV1)
CTRL_SETPT = np.average(pcavsp_ary)
CTRL_OUT = 0
AVG_N = 5    # Taking 5 data samples to average and throw out outliers

# let's get the current value of the phase shifter
PS_INIT = epics.caget(HXR_CAST_PS_PV_R)
# once the script runs, that value is the setpoint
CTRL_OUT = PS_INIT
HXR_FB_EN = epics.caget(HXR_FB_PV)

time_err_ary = np.zeros((AVG_N,))
PCAV_temp_ary = np.zeros(2,)

COUNTER = 0
epics.caput(HB_PV, COUNTER)
TIME_ERR_AVG_PREV = 0
epics.caput(HXR_NAN_PV, 0)
epics.caput(HXR_NAN_PVDESC, 'No NAN read')
print('Controller running')

# Main loop
while True:
    HXR_GAIN = epics.caget(HXR_GAIN_PV)
    PV_PAUSE_TIME = epics.caget(HXR_LOOP_PAUSE_PV)
    loopKp = epics.caget(HXR_LOOP_GAIN_PV)
    COUNTER = epics.caget(HB_PV)
    print(COUNTER)
    for h in range(0, AVG_N):
        PCAV_temp_ary[0,] = epics.caget(HXR_PCAV_PV0)   
        PCAV_temp_ary[1,] = epics.caget(HXR_PCAV_PV0)   # HXR PCAV 1 used for SXR feedback
        PCAV_VAL = np.average(PCAV_temp_ary)
        if np.isNAN(PCAV_VAL):
            PCAV_VAL = 0
        time_err = np.around((CTRL_SETPT - PCAV_VAL), decimals=6)
        time_err_ary[h] = time_err
        time.sleep(0.1)
    time_err_ary_sort = np.sort(time_err_ary)
    time_err_ary_sort1 = time_err_ary_sort[1:-1]    # remove the outliers
    TIME_ERR_AVG = np.mean(time_err_ary_sort1)
    epics.caput(HXR_PCAV_AVG_PV, TIME_ERR_AVG)
    if COUNTER == 0:
        TIME_ERR_DIFF = 0.01
    else:
        TIME_ERR_DIFF = TIME_ERR_AVG_PREV - TIME_ERR_AVG
    print('average error')
    print(TIME_ERR_AVG)
    # cntl_temp = np.true_divide(TIME_ERR_AVG, HXR_GAIN)
    cntl_temp = np.multiply(TIME_ERR_AVG, HXR_GAIN)
    CTRL_DELTA = np.multiply(loopKp, cntl_temp)
    print('previous error')
    print(TIME_ERR_AVG_PREV)
    print('error difference')
    print(TIME_ERR_DIFF)
    HXR_FB_EN = epics.caget(HXR_FB_PV)  # get feedback enable PV
    if (TIME_ERR_DIFF == 0) or (TIME_ERR_DIFF >= 100) or (HXR_FB_EN == 0):
        CTRL_DELTA = 0
    CTRL_OUT = CTRL_OUT + CTRL_DELTA
    print('feedback value')
    print(CTRL_OUT)
    print('feedback delta')
    print(CTRL_DELTA)
    epics.caput(HXR_CAST_PS_PV_W, CTRL_OUT)
    TIME_ERR_AVG_PREV = TIME_ERR_AVG
    COUNTER = COUNTER + 1
    epics.caput(HB_PV, COUNTER)
    now = datetime.datetime.now()
    print(now.strftime('%Y-%m-%d-%H-%M-%S'))
    print('=============================================')
    time.sleep(PAUSE_TIME)