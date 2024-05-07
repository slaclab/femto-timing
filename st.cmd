#!/bin/bash
# As there is no iocBoot directory for the timing python codes,
# we end up running this with IOC set to the name and
# HUTCH set to the lowercase hutch name
# py-fstiming-XXX, py-fstiming-tt-XXX, py-fstiming-pcav-XXX are py2.7
# py-fstiming-cast-XXX is py3
hutch=`echo $IOC | awk -F- '{print $NF;}' -`
base=`basename $IOC -$hutch`

export PSPKG_ROOT=/reg/g/pcds/pkg_mgr
export PSPKG_RELEASE="las-0.0.2"
export EPICS_CA_MAX_ARRAY_BYTES=8000000
source ${PSPKG_ROOT}/etc/set_env.sh

echo "* Starting up, base=${base}"
cd exp-timing

echo "$hutch"

case $base in
   py-fstiming)
      if [[ $hutch = XCS ]]; then
         script=femto_longdelay.py
      else
         script=femto.py
      fi
      export MPLCONFIGDIR=/reg/d/iocData/fstiming
      ;;
   py-fstiming-tt)
      if [[ $hutch = XCS ]]; then
         script=atm2las_fs4.py
      elif [[ $hutch = RIX ]]; then
         script=${hutch}_time_tool.py
      else
         script=time_tool.py
      fi
      export MPLCONFIGDIR=/reg/d/iocData/fstiming-tt
      ;;
   py-fstiming-pcav)
      script=pcav2ttdrift.py
      export MPLCONFIGDIR=/reg/d/iocData/fstiming-pcav
      ;;
   py-fstiming-cast)
      source /reg/g/pcds/setup/epicsenv-3.14.12.sh
      source /cds/group/pcds/pyps/conda/pcds_conda
      script=pcav2cast_${hutch}.py
      export MPLCONFIGDIR=/reg/d/iocData/fstiming-cast-${hutch}
      unset hutch
      ;;
   *)
      echo "Bad IOC name: $IOC"
         while true; do sleep 3600; done     
         # Loop forever so we don't spam the log!
      ;;
esac

echo "Running script $script hutch $hutch"

if [[ $script = pcav2ttdrift.py ]]; then 
   python $script $hutch -T -P || echo "Script exited with code $?"
else
   python $script $hutch || echo "Script exited with code $?" 
fi


