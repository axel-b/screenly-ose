#!/usr/bin/env python
# -*- coding: utf8 -*-

import sys
import subprocess

browser_args = sys.argv[1:]
browser = subprocess.Popen(browser_args, bufsize=-1, stdout=subprocess.PIPE)
while True:
    l = browser.stdout.readline()
    if "VARIABLE_SET" in l or "LOAD_FINISH" in l or "LOAD_ERROR" in l:
        sys.stdout.write(l)
        sys.stdout.flush()
