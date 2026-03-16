#!/bin/bash

# 1. Define the IOC Identity
export IOC="py-fstiming-FS11"
export HUTCH="FS11"

# 2. Set up PCDS Environment (Legacy Python 2.7 / las-0.0.2)
export PSPKG_ROOT=/reg/g/pcds/pkg_mgr
export PSPKG_RELEASE="las-0.0.2"
export EPICS_CA_MAX_ARRAY_BYTES=8000000

# 3. Source the environment (provides psp, Pv, etc.)
if [ -f "${PSPKG_ROOT}/etc/set_env.sh" ]; then
    source ${PSPKG_ROOT}/etc/set_env.sh
else
    echo "ERROR: Environment setup script not found!"
    exit 1
fi

# 4. Navigate to the branch and into the script directory
# Using the absolute path you provided
TOP_DIR="/cds/group/laser/timing/femto-timing/xpp-tpr-patch"
if [ -d "$TOP_DIR/exp-timing" ]; then
    cd "$TOP_DIR/exp-timing"
else
    echo "ERROR: Directory $TOP_DIR/exp-timing not found!"
    exit 1
fi

echo "* Starting simplified Soft IOC: $IOC"
echo "* Working Directory: $(pwd)"
echo "* Python Version: $(python -V 2>&1)"

# 5. Launch the script
# We use 'exec' so the python process correctly receives signals from procServ
if [ -f "femto_tpr.py" ]; then
    echo "* Found femto_tpr.py. Executing..."
    exec python femto_tpr.py $HUTCH
else
    echo "FATAL: femto_tpr.py not found in $(pwd)"
    ls -la
    sleep 30  # Pause to prevent high-frequency restart loops
    exit 1
fi