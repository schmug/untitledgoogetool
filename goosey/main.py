#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""Untitled Goose Tool: Main!
"""

import argparse
import sys
from colored import stylize, attr, fg
import fire

from goosey.auth import auth
from goosey.honk import honk, autohonk
from goosey.conf import genconf
from goosey.csv import goosey_csv
import goosey


def version():
	"""
	Display the version
	"""
	print(f"Untitled Goose Tool Version {goosey.__version__}")


def main():
    fire.Fire({"auth": auth,
               "honk": honk,
               "autohonk": autohonk,
               "conf": genconf,
               "csv": goosey_csv,
               "--version": version})
if __name__ == "__main__":
    main()
