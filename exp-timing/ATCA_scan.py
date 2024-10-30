import time
import sys
from epics import caget, caput, cainfo, PV


class table_ctr_err(Exception):
    """Exception to catch large variations in the relative timing between the Carbide and Amphos."""
    pass


def scan(tgt_time_pv, ctr_time_pv, ph_shft_rbv, table_ctr_pv):
    """Excecutes a time scan and times a 10 ns phase shifter move."""

    #target/counter time dictionaries and initial values
    tgt_time = dict()
    ctr_time = dict()
    tgt = tgt_time_pv.value
    table_ctr = table_ctr_pv.value 

    # scanning parameters 
    init_step = 0.05 # initial step size
    stop = 8 # total number of steps to take
    mult = 10 # multiplier by which to increase/decrease step size after each step
    wait_time = 5 # wait time in seconds b/t steps

    try:
        # time scan
        for x in range(0, stop):
            if (abs(table_ctr-table_ctr_pv.value)>(10^(-6))):
                raise table_ctr_err
            if (x<(stop/2)):
                tgt_time_pv.put(tgt+init_step*(mult**x), wait=True) # step up with increasing step size
            else:
                tgt_time_pv.put(tgt-init_step*(mult**(x-(stop/2))), wait=True) # step down with increasing step size
            time.sleep(wait_time) # wait x sec to update
            tgt_time[x] = tgt_time_pv.value
            ctr_time[x] = ctr_time_pv.value

        #print target/counter time values
        print('Time Error:')
        for x in range(0, stop):
            print(abs(tgt_time[x]-ctr_time[x])) # the absolute value of the difference between the target time and counter time

        # ensure target time is back at initial value
        tgt_time_pv.put(tgt, wait=True)

        # phase shift time measurement
        tgt_time_pv.put(tgt-5, wait=True) # set phase shifter to one side of bucket without getting too close to bucket edge to prevent jumps
        time.sleep(wait_time) # wait to make sure we reach initial time
        move_start = time.time()
        tgt_time_pv.put(tgt+5, wait=True) # move phase shifter to other side of bucket (10 ns move)
        while not((ctr_time_pv.value>(tgt+4.9) and ctr_time_pv.value<(tgt+5.1)) or (ph_shft_rbv.value>4.9 and ph_shft_rbv.value<5.1)): # waits until the counter time and phase shifter RBVs are within +/-0.1 ns of their target values
            if (abs(table_ctr-table_ctr_pv.value)>(10^(-6))):
                raise table_ctr_err
            print(ctr_time_pv.value) # monitor for unexpected jumps in counter time
            pass
        move_stop = time.time()
        move_time = move_stop - move_start # time delay of 10 ns phase shifter move
        print('10ns Move - Phase Shifter Delay Time (s): ', move_time)
        tgt_time_pv.put(tgt, wait=True) # set target time back to initial value

    except table_ctr_err:
        print('Carbide to Amphos timing jumped by more than 1 us. Check Carbide and Amphos for trips.')
