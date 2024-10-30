import time
import sys
from epics import caget, caput, cainfo, PV
from ATCA_scan import scan

# setup PVs
tgt_time_pv = PV('LAS:LHN:LLG2:01:PHASCTL:DELAY_SET') # target time PV
ctr_time_pv = PV('LAS:LHN:LLG2:01:PHASCTL:GET_TIC_NS') # counter time PV
ph_shft_rbv = PV('LAS:LHN:LLG2:01:PHASCTL:RF_PHASE_RBV') # phase shifter position RBV
table_ctr_pv = PV('LAS:OPCPA:CNT:FQ:FREQ_RBCK_RAW') # Agilent tabletop counter RBV - measures delay between Carbide and Amphos pulse trains

# call ATCA scan function
scan(tgt_time_pv, ctr_time_pv, ph_shft_rbv, table_ctr_pv)