import time
import logging
import sys
from epics import caget, caput, cainfo, PV

# setup PVs
tgt_pv = 'LAS:LHN:LLG2:01:PHASCTL:DELAY_SET'
tgt_time_pv = PV('LAS:LHN:LLG2:01:PHASCTL:DELAY_SET')
ctr_time_pv = PV('LAS:LHN:LLG2:01:PHASCTL:GET_TIC_NS')

#target/counter time dictionaries and initial values
tgt_time = dict()
ctr_time = dict()
tgt = tgt_time_pv.value
ctr = ctr_time_pv.value

# scanning parameters 
init_step = 0.05 # initial step size
stop = 8 # total number of steps to take
mult = 10 # multiplier by which to increase/decrease step size after each step
wait_time = 5 # wait time in seconds b/t steps

# time scan
for x in range(0, stop):
    if (x<(stop/2)):
        caput(tgt_pv,tgt+init_step*(mult**x), wait=True) # step up with increasing step size
    else:
        caput(tgt_pv,tgt-init_step*(mult**(x-(stop/2))), wait=True) # step down with increasing step size
    time.sleep(wait_time) # wait x sec to update
    tgt_time[x] = tgt_time_pv.value
    ctr_time[x] = ctr_time_pv.value

#print target/counter time values
print('Target Times:')
for x in range(0, stop): 
    print(tgt_time[x]) # print out all target time values first
print('Counter Times:')
for x in range(0, stop):
    print(ctr_time[x]) # then print out all counter time values

# ensure target time is back at initial value
caput(tgt_pv,tgt, wait=True)

# phase shift time measurement
caput(tgt_pv, tgt-5, wait=True) # set phase shifter to one side of bucket without getting too close to bucket edge to prevent jumps
time.sleep(wait_time) # wait to make sure we reach initial time
move_start = time.time()
caput(tgt_pv, tgt+5, wait=True) # move phase shifter to other side of bucket (10 ns move)
while(ctr_time_pv.value<(tgt+4.9) or ctr_time_pv.value>(tgt+5.1)): # waits until the counter time is within +/-0.1 ns of the target time
    pass
move_stop = time.time()
move_time = move_stop - move_start # time delay of 10 ns phase shifter move
print('10ns Move - Phase Shifter Delay Time (s): ', move_time)
caput(tgt_pv,tgt, wait=True) # set target tinme back to initial value
