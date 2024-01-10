#####################################################################
# Filename: atm2las_fs4.py
# Author: Chengcheng Xu (charliex@slac.stanford.edu)
# Date: 04/28/2021
#####################################################################

import epics as epics
import numpy as np
import time as time
import datetime

pause_time = 0.025
DC_sw_PV  = 'LAS:FS4:VIT:TT_DRIFT_ENABLE'  # Put 0 for disable, put 1 for enable
DC_val_PV = 'LAS:FS4:VIT:matlab:04'        # Drift correct value in ns
ATM_PV = 'XCS:TIMETOOL:TTALL'              # ATM waveform PV
TTC_PV = 'XCS:LAS:MMN:01'                  # ATM mech delay stage
IPM_PV = 'XCS:SB1:BMMON:SUM'               # intensity profile monitor PV
IPM_HI_PV = 'LAS:FS4:VIT:matlab:28.HIGH'
IPM_LO_PV = 'LAS:FS4:VIT:matlab:28.LOW'
TT_time_PV = 'LAS:FS4:VIT:matlab:22'
TT_amp_PV = 'LAS:FS4:VIT:matlab:23'
TT_amp_HI_PV  = str(TT_amp_PV + '.HIGH')
TT_amp_LO_PV  = str(TT_amp_PV + '.LOW')
TT_fwhm_PV = 'LAS:UNDH:FLOAT:14'
TT_fwhm_HI_PV = str(TT_fwhm_PV + '.HIGH')
TT_fwhm_LO_PV = str(TT_fwhm_PV + '.LOW')
LAS_TT_PV = 'LAS:FS4:VIT:FS_TGT_TIME'      # EGU in ns
HXR_CAST_PS_PV_W = 'LAS:UND:MMS:02'        # EGU in ps
HXR_CAST_PS_PV_R = 'LAS:UND:MMS:02.RBV'
SXR_CAST_PS_PV_W = 'LAS:UND:MMS:01'        # EGU in ps
SXR_CAST_PS_PV_R = 'LAS:UND:MMS:01.RBV'
ATM_OFFSET_PV = 'LAS:UNDH:FLOAT:13'        # Notepad PV for ATM setpoint PV in ps
ATM_FB_EN_PV = 'LAS:UNDH:FLOAT:15'         # Using ATM as a feedback
LXT_thre_PV  = 'LAS:UNDH:FLOAT:16'         # Threshold for lxt to move
ATM_FB_GAIN_PV = 'LAS:UNDH:FLOAT:17'
HUTCH_XRAY_ST_PV = 'PPS:FEH1:4:ST01IN'

# ATM Feedback variables
atm_avg_n = 60
atm_val_ary = np.array([0])
ATM_wf_val = epics.caget(ATM_PV)
ATM_pos = ATM_wf_val[0]
ATM_val = ATM_wf_val[1]
ATM_amp = ATM_wf_val[2]
ATM_nxt_amp = ATM_wf_val[3]
ATM_ref_amp = ATM_wf_val[4]
ATM_fwhm = ATM_wf_val[5]
atm_err = 0
atm_ary_mean = 0
atm_ary_mean_fs = 0
atm_pm_step = 0
atm_prev = ATM_val
atm_t_cntr = 1
las_tt_pre = epics.caget(LAS_TT_PV)
atm_offset_pre = epics.caget(ATM_OFFSET_PV)
i_val  = 0
t_old = time.time()
atm_good_thre = 150
atm_bad_thre = 200

# PCAV/CAST feed forward variables 
atm_stat = True
tt_good_cntr = 0
tt_bad_cntr = 0

DC_val = 0
cast_avg_n  = 20    # n sample moving average
time_err_th = 50    # pcav err threshold in fs
time_err_ary = 0 
cast_old = epics.caget(HXR_CAST_PS_PV_R)

cntr = 0

# enabled the drift feedback
epics.caput(DC_sw_PV, 1)

print('Controller running')
while True:
    # Did the LXT move? 
    lxt_thre = epics.caget(LXT_thre_PV)
    las_tt = epics.caget(LAS_TT_PV)
    if np.absolute(las_tt-las_tt_pre) > lxt_thre:
        time.sleep(2)

    # Getting ATM & IPM reading determine if the ATM reading is good    
    hutch_xray_st = epics.caget(HUTCH_XRAY_ST_PV)    
    atm_fb_gain = int(epics.caget(ATM_FB_GAIN_PV))
    atm_wf_tmp = epics.caget(ATM_PV)
    atm_pos = atm_wf_tmp[0]
    atm_val = atm_wf_tmp[1]  # in ps
    atm_amp = atm_wf_tmp[2]
    atm_nxt_amp = atm_wf_tmp[3]
    atm_ref_amp = atm_wf_tmp[4]
    atm_fwhm = atm_wf_tmp[5]
    IPM_val  = epics.caget(IPM_PV)
    atm_offset  = epics.caget(ATM_OFFSET_PV)  # get setpoint in ps
    atm_fb_en = epics.caget(ATM_FB_EN_PV)  # Using feedback?
    # p_term = epics.caget(P_term_PV)
    # i_term = epics.caget(I_term_PV)

    # Get limit threshold from EDM
    ipm_hi_val = epics.caget(IPM_HI_PV)
    ipm_lo_val = epics.caget(IPM_LO_PV)
    tt_amp_hi_val = epics.caget(TT_amp_HI_PV)
    tt_amp_lo_val = epics.caget(TT_amp_LO_PV)
    tt_fwhm_hi_val = epics.caget(TT_fwhm_HI_PV)
    tt_fwhm_lo_val = epics.caget(TT_fwhm_LO_PV)

    if (cntr%(1/pause_time) == 0):
        epics.caput(TT_time_PV, atm_val)
        epics.caput(TT_amp_PV, atm_amp)
        epics.caput(TT_fwhm_PV, atm_fwhm)
    
    cast_val = epics.caget(HXR_CAST_PS_PV_R)
    cast_dif = cast_old - cast_val
    cast_dif_ns = np.true_divide(cast_dif, 1000)

    # Condition for good atm reading
    # if (atm_amp > tt_amhilo_val)and(IPM_val > ipm_lo_val)and(atm_fwhm < ttfwhm_hi)and(atm_fwhm > ttfwhm_lo):
    if (hutch_xray_st==0)and(atm_amp>tt_amp_lo_val)and(atm_fwhm<tt_fwhm_hi_val)and(atm_fwhm>tt_fwhm_lo_val)and(atm_val!=atm_val_ary[-1]):
        tt_good_cntr += 1
        tt_good = True
    else:
        tt_bad_cntr += 1
        tt_good = False
    
    # Determine if use ATM or PCAV as drift compensation
    if (tt_good_cntr > atm_good_thre) and (cntr%(10/pause_time) == 0) :
        atm_stat = True
        tt_good_cntr = 0
        tt_bad_cntr = 0
    elif (tt_bad_cntr > atm_bad_thre) and (cntr%(10/pause_time) == 0) :
        atm_stat = False
        tt_good_cntr = 0
        tt_bad_cntr = 0
    elif (cntr%(20/pause_time) == 0) :
        atm_t_cntr = 1
        tt_good_cntr = 0
        tt_bad_cntr = 0
 
    # Filling the running avg array
    if tt_good:            
        if cntr == 0 and tt_good:
            atm_val_ary[0] = atm_val
        elif (atm_val_ary.size >= atm_avg_n) and tt_good:
            atm_val_ary = np.delete(atm_val_ary, 0)
            atm_val_ary = np.append(atm_val_ary,atm_val)
        else:
            if tt_good:
                atm_val_ary = np.append(atm_val_ary,atm_val)
        # average and convert to fs, ns, also add in the offset 
        atm_ary_mean  = np.mean(atm_val_ary) - atm_offset
        atm_ary_mean_fs = np.around(np.multiply(atm_ary_mean, 1000), 3)
        atm_ary_mean_ns = np.true_divide(atm_ary_mean, 1000)
        atm_err = np.multiply(atm_ary_mean, atm_fb_gain)
        atm_err_ns = np.true_divide(atm_err, 1000)

    if (cntr%(2/pause_time) == 0):
        # epics.caput(TT_amp_PV, atm_amp)  # Update EDM panel
        print('#################################')
        print('ATM array error: ' + str(atm_err) + 'ps')
        print('ATM array mean: ' + str(atm_ary_mean_fs) + 'fs')        
        print('ATM time: ' + str(atm_val))
        print('ATM amp: ' + str(atm_amp) + '  HIGH:' + str(tt_amp_hi_val) + ' LOW:' + str(tt_amp_lo_val))
        print('ATM fwhm: ' + str(atm_fwhm) + '  HIGH:' + str(tt_fwhm_hi_val) + ' LOW:' + str(tt_fwhm_lo_val))
        print('IPM val: ' + str(IPM_val) + '  HIGH:' + str(ipm_hi_val) + ' LOW:' + str(ipm_lo_val))
        print('tt_good_cntr: ' + str(tt_good_cntr))
        print('tt_bad_cntr: ' + str(tt_bad_cntr))
        print('ATM feedback used status: ' + str(atm_fb_en))
        print('ATM offset: ' + str(atm_offset) + 'ps')
        print('+++++++++++++++++++++++++++++++++++++')
        print(atm_val_ary)

    if (atm_val_ary.size == atm_avg_n) and (np.absolute(atm_ary_mean_fs)>time_err_th) and (atm_fb_en != 0):   
        t_now = time.time()
        dt = t_now - t_old
        print('Move to compensate')
        # DC_val = (p_term * atm_err_ns) + (i_term * (i_val + (np.multiply(atm_err_ns, dt))))
        DC_val = epics.caget(DC_val_PV)
        DC_val = DC_val + atm_err_ns
        epics.caput(DC_val_PV, DC_val)
        print('ATM err fs average: ' + str(atm_ary_mean_fs) +'fs')        
        print('ATM err ns average: ' + str(atm_err_ns))        
        print("move DC PV to: " + str(DC_val))
        print('Clearning ATM array')
        atm_val_ary = np.array([0])
        t_old = t_now
    # else:
    #     # DC_val = epics.caget(DC_val_PV)
    #     # DC_val = DC_val + cast_dif_ns
    #     # epics.caput(DC_val_PV, DC_val)
        
    #     if (cntr%(2/pause_time) == 0):
    #         print('#################################')
    #         print('Bad atm shots')
    #         print('#################################')
    #         print('ATM array error: ' + str(atm_err) + 'ps')
    #         print('ATM array mean: ' + str(atm_ary_mean_fs) + 'fs')        
    #         print('ATM time: ' + str(atm_val))
    #         print('ATM amp: ' + str(atm_amp) + '  HIGH:' + str(tt_amp_hi_val) + ' LOW:' + str(tt_amp_lo_val))
    #         print('ATM fwhm: ' + str(atm_fwhm) + '  HIGH:' + str(tt_fwhm_hi_val) + ' LOW:' + str(tt_fwhm_lo_val))
    #         print('IPM val: ' + str(IPM_val) + '  HIGH:' + str(ipm_hi_val) + ' LOW:' + str(ipm_lo_val))
    #         print('tt_good_cntr: ' + str(tt_good_cntr))
    #         print('tt_bad_cntr: ' + str(tt_bad_cntr))
    #         print('ATM feedback used status: ' + str(atm_fb_en))    
    #         print('+++++++++++++++++++++++++++++++++++++')
    #         print(atm_val_ary)                    
    #         # print(np.multiply(cast_dif,1000))
    #         # print('tt_good_cntr: ' + str(tt_good_cntr))
    #         # print('tt_bad_cntr: ' + str(tt_bad_cntr))
    


    if (cntr%(60/pause_time) == 0):
        print('//////////////////////////////////////////////////////////////////')
        print('Counter val: ' + str(cntr))
        ts = time.strftime('%Y-%m-%d-%H:%M:%S', time.localtime())
        print(ts)

    atm_offset_pre = atm_offset
    cast_old = cast_val
    las_tt_pre = las_tt
    cntr += 1
    time.sleep(pause_time)
    