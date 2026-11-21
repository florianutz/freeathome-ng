---
name: Bug report
about: Create a report to help us improve free@home NG
title: "[Bug] "
labels: bug
assignees: ""
---

## Description
A clear and concise description of what the bug is.

## Environment
- Home Assistant version:
- free@home NG version:
- SysAP model & firmware version (must be >= 2.6.0):
- Running alongside classic `freeathome` integration? (yes / no)

## Reproduction Steps
1. ...
2. ...

## Logs / Config Dump
Please attach the output of the `freeathome_ng.dump_config` or `freeathome_ng.monitor` action if relevant. A dump contains your device and room names and serial numbers: anonymise it first with `python3 scripts/anonymize_dump.py <dump.json> -o <dump_anon.json>` from this repository, or attach only the affected devices.
