#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""Untitled Goose Tool: Honk!
This module performs data collection of various data sources from a Google Workspace / GCP environment.
"""

import aiohttp
import asyncio
import configparser
import json
import os
import sys
import time
import warnings
from multiprocessing import Process

from goosey.google_directory_dumper import GoogleDirectoryDumper
from goosey.gmail_dumper import GmailDumper
from goosey.gcp_dumper import GCPDataDumper
from goosey.alert_center_dumper import AlertCenterDumper
from goosey.datadumper import DataDumper
from goosey.utils import *
from goosey.auth import auth as gooseyauth, get_google_credentials

if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

warnings.simplefilter('ignore')

logger = setup_logger(__name__, debug=False)
data_calls = {}

async def run(args, config, auth, init_sections):
    """Main async run loop

    :param args: argparse object with populated namespace
    :type args: Namespace argparse object
    :param auth: All auth credentials
    :type auth: dict
    :param init_sections: Sections to initialize
    :type init_sections: list
    :return: None
    :rtype: None
    """
    global data_calls, logger

    # Set name of current task
    asyncio.current_task().set_name("honk_run")

    session = aiohttp.ClientSession(trust_env=True)

    # Build Google credentials from auth data
    google_auth = auth.get('google_auth', {})
    credentials = get_google_credentials(google_auth)

    maindumper = DataDumper(args.output_dir, args.reports_dir, {}, session, args.debug)

    directory, gmail, gcp, alerts = False, False, False, False

    if args.dry_run:
        directory_dumper = maindumper
        gmail_dumper = maindumper
        gcp_dumper = maindumper
        alerts_dumper = maindumper
    else:
        if 'directory' in init_sections:
            directory_dumper = GoogleDirectoryDumper(
                args.output_dir, args.reports_dir, credentials,
                maindumper.ahsession, config, args.debug
            )
            directory = True
        if 'gmail' in init_sections:
            gmail_dumper = GmailDumper(
                args.output_dir, args.reports_dir, credentials,
                maindumper.ahsession, config, args.debug
            )
            gmail = True
        if 'gcp' in init_sections:
            gcp_dumper = GCPDataDumper(
                args.output_dir, args.reports_dir, credentials,
                maindumper.ahsession, config, args.debug
            )
            gcp = True
        if 'alerts' in init_sections:
            alerts_dumper = AlertCenterDumper(
                args.output_dir, args.reports_dir, credentials,
                maindumper.ahsession, config, args.debug
            )
            alerts = True

    async with maindumper.ahsession as ahsession:
        tasks = []
        if directory:
            tasks.extend(directory_dumper.data_dump(data_calls['directory'], "directory"))
        if gmail:
            tasks.extend(gmail_dumper.data_dump(data_calls['gmail'], "gmail"))
        if gcp:
            tasks.extend(gcp_dumper.data_dump(data_calls['gcp'], "gcp"))
        if alerts:
            tasks.extend(alerts_dumper.data_dump(data_calls['alerts'], "alerts"))

        honk_results = await asyncio.gather(*tasks)
        error_occured = False
        for class_name, func_name, err in honk_results:
            if err:
                logger.error(f"[{class_name}] {func_name[5:]}: Failed with error {err}")
                error_occured = True
            else:
                logger.info(f"[{class_name}] {func_name[5:]}: Success")
        if error_occured:
            sys.exit(1)

def _get_section_dict(config, s):
    try:
        return dict([(x[0], x[1].lower()=='true') for x in config.items(s)])
    except Exception as e:
        logger.warning(f'Error getting section dictionary from config: {str(e)}')
    return {}

def parse_config(configfile, args, auth=None):
    global data_calls
    config = configparser.ConfigParser()
    config.read(configfile)

    if not auth:
        sections = ['directory', 'gmail', 'gcp', 'alerts']
    else:
        sections = ['auth']

    init_sections = []
    for section in sections:
        d = _get_section_dict(config, section)
        data_calls[section] = {}
        for key in d:
            if d[key]:
                data_calls[section][key] = True
                init_sections.append(section)

    if args.directory:
        for item in [x.replace('dump_', '') for x in dir(GoogleDirectoryDumper) if x.startswith('dump_')]:
            data_calls['directory'][item] = True
        init_sections.append("directory")
    if args.gmail:
        for item in [x.replace('dump_', '') for x in dir(GmailDumper) if x.startswith('dump_')]:
            data_calls['gmail'][item] = True
        init_sections.append("gmail")
    if args.gcp:
        for item in [x.replace('dump_', '') for x in dir(GCPDataDumper) if x.startswith('dump_')]:
            data_calls['gcp'][item] = True
        init_sections.append("gcp")
    if args.alerts:
        for item in [x.replace('dump_', '') for x in dir(AlertCenterDumper) if x.startswith('dump_')]:
            data_calls['alerts'][item] = True
        init_sections.append("alerts")

    logger.debug(json.dumps(data_calls, indent=2))
    return config, init_sections

def honk(authfile=".ugt_auth",
         config=".conf",
         auth=".auth",
         output_dir="output",
         reports_dir="reports",
         debug=False,
         dry_run=False,
         directory=False,
         gmail=False,
         gcp=False,
         alerts=False,
         encryption_pw=None):
    """
    Untitled Goose Tool Information Gathering (Google Workspace)

    Args:
        authfile: File to store the authentication tokens and cookies
        config: Path to config file
        auth: File to store the credentials used for authentication
        output_dir: Directory for storing the results
        reports_dir: Directory for storing debugging/informational logs
        debug: Enable debug logging
        dry_run: Dry run (do not do any API calls)
        directory: Set all of the Google Directory calls to true
        gmail: Set all of the Gmail calls to true
        gcp: Set all of the GCP calls to true
        alerts: Set all of the Alert Center calls to true
        encryption_pw: Password for the auth file encryption. SHOULD ONLY BE USED WITH AUTOHONK
    """
    global logger
    args = dict2obj(locals())

    logger = setup_logger(__name__, args.debug)

    auth_un_pw, auth_data = get_authfile(authfile=args.auth, ugt_authfile=args.authfile, logger=logger, encryption_pw=encryption_pw)

    check_output_dir(args.output_dir, logger)
    check_output_dir(args.reports_dir, logger)
    check_output_dir(f'{args.output_dir}{os.path.sep}directory', logger)
    check_output_dir(f'{args.output_dir}{os.path.sep}gmail', logger)
    check_output_dir(f'{args.output_dir}{os.path.sep}gcp', logger)
    check_output_dir(f'{args.output_dir}{os.path.sep}alerts', logger)
    config, init_sections = parse_config(args.config, args)

    logger.info("Goosey beginning to honk.")
    seconds = time.perf_counter()
    try:
        asyncio.run(run(args, config, auth_data, init_sections))
    except RuntimeError as e:
        sys.exit(1)
    elapsed = time.perf_counter() - seconds
    logger.info("Goosey executed in {0:0.2f} seconds.".format(elapsed))

def autohonk(authfile=".ugt_auth",
         config=".conf",
         auth=".auth",
         output_dir="output",
         reports_dir="reports",
         debug=False,
         directory=False,
         gmail=False,
         gcp=False,
         alerts=False,
         insecure=False):
    """
    Untitled Goose Tool Information Gathering. With auto authentication!
    This will never stop until you tell it to.

    Args:
        authfile: File to store the authentication tokens and cookies
        config: Path to config file
        auth: File to store the credentials used for authentication
        output_dir: Directory for storing the results
        reports_dir: Directory for storing debugging/informational logs
        debug: Enable debug logging
        directory: Set all of the Google Directory calls to true
        gmail: Set all of the Gmail calls to true
        gcp: Set all of the GCP calls to true
        alerts: Set all of the Alert Center calls to true
        insecure: Disable secure authentication handling (file encryption)
    """
    # auth and honk in a loop
    encryption_pw = None
    if not insecure:
        encryption_pw = getpass.getpass("Please type the password for file encryption: ")
    auth_dict = {
        "authfile": authfile,
        "config": config,
        "auth": auth,
        "debug": debug,
        "encryption_pw": encryption_pw
    }
    honk_dict = {
        "authfile": authfile,
        "config": config,
        "auth": auth,
        "output_dir": output_dir,
        "reports_dir": reports_dir,
        "debug": debug,
        "directory": directory,
        "gmail": gmail,
        "gcp": gcp,
        "alerts": alerts,
        "encryption_pw": encryption_pw
    }
    # Endless loop to keep authing and honking
    while True:
        auth_process = Process(target=gooseyauth, kwargs=auth_dict)
        auth_process.start()
        auth_process.join()

        honk_process = Process(target=honk, kwargs=honk_dict)
        seconds = time.perf_counter()

        honk_process.start()
        honk_process.join()

        elapsed = time.perf_counter() - seconds
        if elapsed <= 5:
            break
