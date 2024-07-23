#####################################################################
# Filename: pcav2cast_sxr.py
# Author: Chengcheng Xu (charliex@slac.stanford.edu)
# Date: 03/07/2021
#####################################################################
# This script will take the phase cavity value and put throw 
# an exponential feedback controller, then output its value to the 
# phase shifter in the cable stabilizer system
# NOTE: This is a band-aid, code is probably breaking many rules
# source /reg/g/pcds/engineering_tools/xpp/scripts/pcds_conda 
# to run python on las-console

import epics as epics
import numpy as np
import time as time
import datetime

######################################
# HXR PV definition
######################################
HB_PV = 'LAS:UNDH:FLOAT:90'
HXR_FB_PV = 'LAS:UNDH:FLOAT:05'
HXR_NaN_alert_PV = 'LAS:UNDH:FLOAT:91'
SXR_NaN_alert_PVDESC = HXR_NaN_alert_PV + '.DESC'
HXR_CAST2PCAV_Gain_PV = 'LAS:UNDH:FLOAT:92'
HXR_pcav2cast_loopKp_PV = 'LAS:UNDH:FLOAT:93'
HXR_pcav2cast_loopPausetime_PV = 'LAS:UNDH:FLOAT:94'
HXR_PCAV_PV0 = 'SIOC:UNDH:PT01:0:TIME0'
HXR_PCAV_PV1 = 'SIOC:UNDH:PT01:0:TIME1'
HXR_PCAV_AVG_PV = 'LAS:UNDH:FLOAT:06'
HXR_CAST_PS_PV_W = 'LAS:UND:MMS:02'
HXR_CAST_PS_PV_R = HXR_CAST_PS_PV_W + '.RBV'

# HXR_CAST2PCAV_Gain = 1.1283 # the slope from plotting cast phase shifter to value read from PCAV
HXR_CAST2PCAV_Gain = 2 #03/1/2024 cal

######################################
# SXR PV definition
######################################
HB_PV = 'LAS:UNDS:FLOAT:90'
SXR_NaN_alert_PV = 'LAS:UNDS:FLOAT:91'
SXR_NaN_alert_PVDESC = SXR_NaN_alert_PV + '.DESC'
SXR_CAST2PCAV_Gain_PV = 'LAS:UNDS:FLOAT:92'
SXR_pcav2cast_loopKp_PV = 'LAS:UNDS:FLOAT:93'
SXR_pcav2cast_loopPausetime_PV = 'LAS:UNDS:FLOAT:94'
SXR_FB_PV = 'LAS:UNDS:FLOAT:05'
SXR_PCAV_PV0 = 'SIOC:UNDS:PT01:0:TIME0'
SXR_PCAV_PV1 = 'SIOC:UNDS:PT01:0:TIME1'
SXR_CAST_PS_PV_W = 'LAS:UND:MMS:01'
SXR_CAST_PS_PV_R = SXR_CAST_PS_PV_W + '.RBV'
SXR_CAST2PCAV_Gain = 1.1283 # the slow from plotting cast phase shifter to value read from PCAV
SXR_PCAV_AVG_PV = 'LAS:UNDS:FLOAT:06'
XPP_Switch_PV = 'LAS:UNDS:FLOAT:95'
XPP_FeedforwardKp_PV = 'LAS:UNDS:FLOAT:96'
# -1727400.6755412123

# init values
XPP_feedforwardKp = 1.0
pcav2cast_loopPausetime = 5    # Let's give some time for the system to react
pcav2cast_loopKp = 0.1   # Feed back loop gain
#We are doing an exponential fb loop, where the output = output[-1] + (-gain * error)
pcavsp_ary   = np.zeros(2,)
pcavsp_ary[0,]  = epics.caget(SXR_PCAV_PV0)  # Latch in the value before starting the feedback, this will be value we correct to
pcavsp_ary[1,]  = epics.caget(SXR_PCAV_PV1)  # Latch in the value before starting the feedback, this will be value we correct to
Cntl_setpt = np.average(pcavsp_ary)
Cntl_output = 0
pcav_avg_n  = 5    # Taking 5 data samples to average and throw out outliers

pause_time = 2    # Let's give some time for the system to react
Cntl_gain = 0.1   # Feed back loop gain
#We are doing an exponential fb loop, where the output = output[-1] + (-gain * error)
Cntl_setpt  = epics.caget(SXR_PCAV_PV0)  # Latch in the value before starting the feedback, this will be value we correct to
Cntl_output = 0
pcav_avg_n  = 5    # Taking 5 data samples to average and throw out outliers

# let's get the current value of the phase shifter
SXR_CAST_PS_init_Val = epics.caget(SXR_CAST_PS_PV_R)
Cntl_output = SXR_CAST_PS_init_Val   # once the script runs, that value is the setpoint
sxr_fb_en = epics.caget(SXR_FB_PV)

time_err_ary = np.zeros((pcav_avg_n,)) 
PCAV_temp_ary = np.zeros(2,)

cntr = 0
NaN_alert_val = 0
time_err_avg_prev = 0
epics.caput(HB_PV, cntr)
epics.caput(SXR_NaN_alert_PV, 0)
epics.caput(SXR_NaN_alert_PVDESC, 'No NaN read')
# epics.caput()
# epics.caput()
time_err_avg_prev = 0

print('Controller running')

while True:
    SXR_CAST2PCAV_Gain = epics.caget(SXR_CAST2PCAV_Gain_PV)
    pcav2cast_loopPausetime = epics.caget(SXR_pcav2cast_loopPausetime_PV)
    pcav2cast_loopKp = epics.caget(SXR_pcav2cast_loopKp_PV)
    cntr = epics.caget(HB_PV)
    XPP_feedforwardKp = epics.caget(XPP_FeedforwardKp_PV)
    print(cntr)
    for h in range(0,pcav_avg_n):
        PCAV_temp_ary[0,] = epics.caget(SXR_PCAV_PV0)
        PCAV_temp_ary[1,] = epics.caget(SXR_PCAV_PV1)
        SXR_PCAV_Val_tmp = np.average(PCAV_temp_ary)
        # SXR_PCAV_Val_tmp = epics.caget(SXR_PCAV_PV0)
        if np.isnan(SXR_PCAV_Val_tmp):
            SXR_PCAV_Val_tmp = 0
            NaN_alert_val = 1
        time_err = np.around((Cntl_setpt - SXR_PCAV_Val_tmp), decimals=6)
        time_err_ary[h] = time_err
        time.sleep(0.1)
    if NaN_alert_val == 1:
        epics.caput(SXR_NaN_alert_PV, NaN_alert_val)
        epics.caput(SXR_NaN_alert_PVDESC, "NaN Detected")
    else:
        epics.caput(SXR_NaN_alert_PV, NaN_alert_val)
        epics.caput(SXR_NaN_alert_PVDESC, "No NaN")        
    time_err_ary_sort = np.sort(time_err_ary)
    time_err_ary_sort1 = time_err_ary_sort[1:-1]
    time_err_avg = np.mean(time_err_ary_sort1)  
    epics.caput(SXR_PCAV_AVG_PV, time_err_avg)

    if cntr == 0:
        time_err_diff = 0.01
    else:
        time_err_diff = time_err_avg_prev - time_err_avg  
    print('average error')
    print(time_err_avg)
    cntl_temp = np.true_divide(time_err_avg, SXR_CAST2PCAV_Gain)    
    cntl_temp = np.multiply(time_err_avg, SXR_CAST2PCAV_Gain)
    cntl_delta = np.multiply(pcav2cast_loopKp, cntl_temp)    
    print('previous error')
    print(time_err_avg_prev)
    print('Error diff')
    print(time_err_diff)
    sxr_fb_en = epics.caget(SXR_FB_PV)
    if (time_err_diff == 0) or (time_err_diff >= 100) or (sxr_fb_en == 0):
        cntl_delta = 0
    XPP_Switch_val = epics.caget(XPP_Switch_PV)
    if (XPP_Switch_val != 0):
        hxr_cast_val = epics.caget(HXR_CAST_PS_PV_R)
        print('NEH RF Ref following HXR PCAV')
        Cntl_output = np.multiply(hxr_cast_val, XPP_feedforwardKp)
    else:
        Cntl_output = Cntl_output + cntl_delta
    print('feedback value')
    print(Cntl_output)
    print('feedback delta')
    print(cntl_delta)
    epics.caput(SXR_CAST_PS_PV_W, Cntl_output)
    time_err_avg_prev = time_err_avg
    cntr = cntr + 1
    epics.caput(HB_PV, cntr)
    now = datetime.datetime.now()
    print(now.strftime('%Y-%m-%d-%H-%M-%S'))
    print('=============================================')        
    time.sleep(pause_time)  

# epics.caput(SXR_CAST_PS_PV_W, SXR_CAST_PS_init_Val)
