# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

LCLS-I femtosecond-timing (`fstiming`) control scripts. Each script is a long-running EPICS soft-IOC loop that locks/steers laser timing by reading and writing PVs. There is no build system, package manifest, or test suite — these are operational scripts run directly by IOCs on the SLAC controls network. All real "data" lives in EPICS PVs, so behavior can only be fully exercised against live (or simulated) PVs, not locally.

## Running

`st.cmd` is the IOC entry point. It derives the script and hutch from the `$IOC` environment variable (`<base>-<hutch>`, e.g. `py-fstiming-pcav-xcs`) and dispatches:

- `py-fstiming` → `femto.py` (or `femto_longdelay.py` for XCS) — the main locker loop
- `py-fstiming-tt` → `time_tool.py` (or `atm2las_fs4.py` for XCS, `RIX_time_tool.py` for RIX) — time-tool drift signal
- `py-fstiming-pcav` → `pcav2ttdrift.py` — PCAV-based drift signal (run with `-T -P`)
- `py-fstiming-cast` → `pcav2cast_<hutch>.py` — CAST phase-shifter feedback (Python 3)

Scripts take the system/hutch name as `argv[1]` and can be run manually for debugging, e.g. `python femto.py XCS`. With no argument they prompt (femto) or exit (others).

**Python split:** `femto*.py`, `time_tool.py`, `pcav2ttdrift.py`, and the py2 `watchdog.py` are **Python 2.7** (note `print` statements, `<>` operator). `pcav2cast_*.py` and `watchdog3.py` are **Python 3** (use `pyepics`/`epics` + conda env, sourced in `st.cmd` for the cast case). Do not "modernize" py2 syntax unless migrating a whole script — the IOCs pin the interpreter.

## Two EPICS access layers

This repo mixes two incompatible PV libraries; match whichever the file already uses:
- **`psp.Pv`** (`from psp.Pv import Pv`) — used by `femto.py`, `time_tool.py`, `pcav2ttdrift.py`. Connect, then `.get(ctrl=True, timeout=...)` / `.put(...)`, read `.value`.
- **`pyepics`** (`import epics` / `from epics import ...`) — used by `pcav2cast_*.py`, `scan.py`, `watchdog3.py`. Module-level `caget`/`caput`.

## Configuration

`femto.py` reads per-locker JSON config (`<HUTCH>_locker_config.json`) selected by hutch name. Each defines `nm`, PV `base` prefix, `laser_trigger` EVR PV, `drift_correction_dir`, and the `use_drift_correction`/`use_dither` toggles. `PVS.path` in `femto.py` hardcodes the deployed config directory (`/cds/group/laser/timing/femto-timing/dev/exp-timing/`). Other scripts (`time_tool.py`, `pcav2ttdrift.py`, `pcav2cast_*.py`) hardcode hutch→PV mappings inline in `if/elif` blocks rather than using JSON.

## Architecture of the main locker (femto.py)

`femto()` builds a `PVS` (all PV handles for one locker) + `watchdog`, then loops: check watchdog → `locker_status()` (RF/diode/frequency/lock health) → optional `calibrate()` → `check_jump()` → `fix_jump()` → `set_time()`. Key helper classes: `locker` (the control logic), `sawtooth` (maps phase-motor position + trigger + delay/offset to laser time across the 68 MHz Vitara period), `time_interval_counter` (SR620 readback with a `ring` buffer for stability/jitter gating), `phase_motor`, `trigger`, `degrees_s` (keeps ns ↔ S-band degrees in sync). The unit convention is **nanoseconds everywhere except the phase motor, which is in picoseconds** (`scale = .001`).

Drift correction is feed-forward: the `*-tt`/`*-pcav` scripts compute a drift signal and write it to `DRIFT_CORRECT_SIG`; `femto.py`'s `set_time()` reads it back (gated by `use_drift_correction`) and nudges the phase motor.

## Watchdog cooperative-exit protocol

Every loop script shares a `watchdog` PV. On each `check()` the script increments the PV; if it reads back a value it didn't write (someone else incremented) or a negative value, it sets `self.error = 1` and exits. This is how duplicate instances are prevented and how an IOC is told to stop — preserve this contract when editing loops.

## PCAV→CAST feedback (pcav2cast_sxr.py / pcav2cast_hxr.py)

These two files are diverged copies of the same exponential feedback loop (`CTRL_OUT += LOOP_KP * gain * TIME_ERR_AVG`). The feedback gate **must** keep the `TIME_ERR_DIFF == 0` term:

```python
if (TIME_ERR_DIFF == 0) or (abs(TIME_ERR_DIFF) >= TIME_ERR_THRESH) or (FB_EN == 0):
    CTRL_DELTA = 0
```

A frozen PCAV PV returns a constant (non-`NaN`) value, so the `NaN` guard misses it and the error difference goes to 0; without the `== 0` term the loop integrates `CTRL_OUT` indefinitely and drives the phase shifter away (runaway observed 2026-06-11). It was once removed from SXR as "unused" — it does not feed the delta math but is the staleness interlock. SXR feeds back on PCAV `TIME1` and has XPP-switch follow logic; HXR uses `TIME0`.

## Deployment

Edits in this checkout do **not** affect running IOCs. Per `README.md`: develop in `dev/` or a fork, commit, tag, and push; then a new tagged clone is created under `/cds/group/laser/timing/femto-timing/<tag>` that the IOCs point at. So a fix isn't live until it's tagged, redeployed, and the IOC restarted.
