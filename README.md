# LCLS-I Femtosecond Timing (fstiming)

Operational scripts for LCLS-I laser timing control. Each script runs as a long-running EPICS soft-IOC loop on the LCLS controls network.

## Scripts

| Script | Purpose | Python | EPICS Layer |
|--------|---------|--------|-------------|
| `femto.py` | Main locker loop (all hutches except XCS) | 2.7 | psp.Pv |
| `femto_longdelay.py` | Main locker loop (XCS) | 2.7 | psp.Pv |
| `time_tool.py` | Time-tool drift correction signal | 2.7 | psp.Pv |
| `pcav2cast_hxr.py` | PCAV-to-CAST phase-shifter feedback (HXR) | 3 | pyepics |
| `pcav2cast_sxr.py` | PCAV-to-CAST phase-shifter feedback (SXR) | 3 | pyepics |

## Configuration

Per-hutch JSON config files (`<HUTCH>_locker_config.json`) define locker parameters: PV base prefix, laser trigger PV, drift correction direction, and feature toggles. Supported hutches: CXI, XPP, MEC, MFX, XCS.

## Running

`st.cmd` is the IOC entry point. It derives the script and hutch from the `$IOC` environment variable (`<base>-<hutch>`, e.g. `py-fstiming-cast-sxr`) and dispatches accordingly:

| IOC base | Script |
|----------|--------|
| `py-fstiming` | `femto.py` (or `femto_longdelay.py` for XCS) |
| `py-fstiming-tt` | `time_tool.py` |
| `py-fstiming-cast` | `pcav2cast_<hutch>.py` |

## Deployment

Edits in a working checkout do not affect running IOCs. To test:

1. Develop in a fork or the `dev/` directory
2. Commit, and push:
   ```bash
   git commit -m "message"
   git push origin
   ```
3. Point the IOC at the dev directory and restart

## Documentation

- [Femto resource guide](https://confluence.slac.stanford.edu/x/mYM6Gw)
- [Managing the Femto Scripts](https://confluence.slac.stanford.edu/x/F7p8F)
