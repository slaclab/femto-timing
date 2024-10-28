import time
import logging
import sys
from epics import caget, caput, cainfo, PV

# logging.basicConfig(
#                 format='%(asctime)s - %(levelname)s - %(message)s',
#                 style='%',
#                 datefmt='%Y-%m-%d %H:%M',
#                 level=logging.DEBUG,
#                 filename=str('/reg/d/iocData/py-fstiming-XCS/iocInfo/scan.log'),
#                 filemode='a',
#             )

# setup PVs
tgt_pv = 'LAS:LHN:LLG2:02:PHASCTL:DELAY_SET'
tgt_time_pv = PV('LAS:LHN:LLG2:02:PHASCTL:DELAY_SET')
ctr_time_pv = PV('LAS:LHN:LLG2:02:PHASCTL:GET_TIC_NS')

#target/counter time dictionaries
tgt_time = dict()
ctr_time = dict()

# scanning parameters 
init_step = 0.05 # initial step size
stop = 8 # total number of steps to take
mult = 10 # multiplier by which to increase/decrease step size after each step
wait_time = 5 # wait time in seconds b/t steps

# print current tgt and ctr time
tgt = tgt_time_pv.value
print(tgt)
# logging.info('%s', tgt)
ctr = ctr_time_pv.value
print(ctr)
# logging.info('%s', ctr)

# scan through ns steps
for x in range(0, stop):
    if (x<(stop/2)):
        caput(tgt_pv,tgt+init_step*(mult^x), wait=True) # step up with increasing step size
    else:
        caput(tgt_pv,tgt-init_step*(mult^(x-(stop/2))), wait=True) # step down with increasing step size
    time.sleep(wait_time) # wait x sec to update
    tgt_time[x] = tgt_time_pv.value
    ctr_time[x] = ctr_time_pv.value

#print target/counter time values
print('Target Times:')
#logging.info('Target Times:')
for x in range(0, stop): 
    print(tgt_time[x]) # print out all target time values first
    # logging.info('%s', tgt_time[x])
print('Counter Times:')
#logging.info('Counter Times:')
for x in range(0, stop):
    print(ctr_time[x]) # then print out all counter time values
    # logging.info('%s', ctr_time[x])

# write back orig tgt time 
print(tgt)
# logging.info('%s', tgt)
caput(tgt_pv,tgt, wait=True)
