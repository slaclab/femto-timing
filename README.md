<h1 align="center">LCLS-I fstiming scripts</h1>

<div align="center">
  <strong>LCLS-I fstiming </strong>
</div>

<p align="center">
  <a href="#motivation">Motivation</a> •
  <a href="#features">Features</a> •
  <a href="#basic-usage">Basic Usage</a> •
  <a href="https://confluence.slac.stanford.edu/display/timing/launch+femto.py">Documentation</a>
</p>

## Motivation
Repository for all LCLS-I fstiming scripts

## Features
* femto.py: **TO DO**
* atm2las.py: **TO DO**
* pcav2cast.py: **TO DO**
* pcav2ttdrift.py: **TO DO**
* time_tool.py: **TO DO**
* watchdog.py: **TO DO**

## Basic Usage
**TO DO**

[femto resource guide](https://confluence.slac.stanford.edu/x/mYM6Gw)

Note, any changes that are done should be in the **dev** directory, not in any of the released directories. The **dev** folder is where any unmerged changes should occur. Better yet, in a fork. While making changes, please keep in mind to make periodic commits to track changes. Once an update is ready to be released, please tag it and push.
```bash
   # /cds/group/laser/las-dev/<user_name>/<forked_repo>
   # or
   # /cds/group/laser/timing/femto-timing/dev
   git commit -m "message"
   git tag
   git push tag
```
Once approved and merged, a new local repository directory needs to be created so the "IOCs" can point to it. There are two ways to go about this. Option A is a one line command. The only thing that needs chagning is the "<tag name>" variable at the beginning. Option B is the same command, only broken up. Could be helpful if there are any issues with the git checkout process that needs troubleshooting. 
```bash
   # /cds/group/laser/timing/femto-timing
   # Option A
   TAG=<tag name> bash -c 'git clone -c advice.detachedHead=false --branch $TAG --single-branch https://github.com/slaclab/femto-timing.git $TAG'
   # Option B
   git clone --single-branch https://github.com/slaclab/femto-timing.git <tag name>
   cd <tag name>
   git checkout <tag name>
```
