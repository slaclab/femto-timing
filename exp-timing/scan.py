import time
from epics import caget, caput, cainfo, PV

# setup PVs
tgt_pv = 'LAS:FS4:VIT:FS_TGT_TIME'
tgt_time_pv = PV('LAS:FS4:VIT:FS_TGT_TIME')
ctr_time_pv = PV('LAS:FS4:VIT:FS_CTR_TIME')

# scanning parameters 
stop = 10 # scan range ns
step = 1 # scan step interval in ns 
direction = -1 # -1 for down, 1 for up 
wait_time = 5 # wait time in seconds b/t steps

# print current tgt and ctr time
tgt = tgt_time_pv.value
print(tgt)
ctr = ctr_time_pv.value
print(ctr)

# scan through ns steps
for x in range(0, stop, step):
    caput(tgt_pv,tgt+x*direction, wait=True)
    time.sleep(wait_time) # wait x sec to update
    # printout the values to see on the terminal 
    print(tgt_time_pv.value)
    print(ctr_time_pv.value)

# write back orig tgt time 
print(tgt)
caput(tgt_pv,tgt, wait=True)
