#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""Untitled Goose Tool: generate_conf
This script creates a blank configuration file to use with Google Workspace.
"""
import configparser
import fire
import getpass
from docstring_parser import parse
from docstring_parser.common import DocstringStyle
from goosey.utils import *

from goosey.google_directory_dumper import GoogleDirectoryDumper
from goosey.gmail_dumper import GmailDumper
from goosey.gcp_dumper import GCPDataDumper
from goosey.alert_center_dumper import AlertCenterDumper

def genconfstring(args, docstring_params, section_name, prefix, config_dict={}):
    conf_s = f"[{section_name}]\n"
    for arg_key in args.keys():
        if arg_key.startswith(prefix):
            var_name = arg_key[len(prefix):]
            val = args[arg_key]
            if val == None and section_name in config_dict and var_name in config_dict[section_name]:
                val = config_dict[section_name][var_name]
            if val == None:
                val = ""
            if arg_key in docstring_params:
                desc = docstring_params[arg_key]
                conf_s += f"# {desc}\n"
            conf_s += f"{var_name}={val}\n"
    conf_s += "\n"
    return conf_s


def genconf(outpath_auth=".auth",
            outpath_conf=".conf",
            auth_service_account_file=None,
            auth_subject=None,
            config_customer_id=None,
            config_domain=None,
            config_gcp_projects="All",
            filters_date_start=None,
            filters_date_end=None,
            directory=False,
            gmail=False,
            gcp=False,
            alerts=False,
            dict_config={},
            new=False,
            insecure=False,
            debug=False):
    """
    Generate Configuration Files for Goose (Google Workspace)

    Args:
        outpath_auth: Path to output the auth config
        outpath_conf: Path to output the goose config
        auth_service_account_file: Path to the Google service account JSON key file
        auth_subject: Admin email for domain-wide delegation
        config_customer_id: Google Workspace customer ID (or 'my_customer' for the default)
        config_domain: Your Google Workspace domain
        config_gcp_projects: Comma-separated GCP project IDs, or 'All' for all accessible projects
        filters_date_start: Format should be YYYY-MM-DD. If not set will default to the earliest available
        filters_date_end: Format should be YYYY-MM-DD. Will default to the present day
        directory: Enable all Google Workspace Directory log collection
        gmail: Enable all Gmail log collection
        gcp: Enable all GCP log collection
        alerts: Enable all Alert Center log collection
        dict_config: dictionary of config values you want to set
        new: Overwrite the existing config
        insecure: Disable secure authentication handling (file encryption)
        debug: Enable debug logging
    """
    # Grab arguments as a dictionary object
    args = locals()
    # parse the docstring for arguments so they can be used as comments
    docstring = parse(genconf.__doc__)

    logger = setup_logger(__name__, args["debug"])

    # Generate dictionary of descriptions for each parameter
    docstring_params = {}
    for param in docstring.params:
        docstring_params[param.arg_name] = param.description

    # check if authfile exists.
    if not ((args["insecure"] and os.path.isfile(outpath_auth)) or \
            os.path.isfile(outpath_auth + ".aes")):
        # If service account file not provided, prompt for it
        if not args["auth_service_account_file"]:
            args["auth_service_account_file"] = input("Enter the path to the Google service account JSON key file: ")

        # If subject not provided, prompt for it
        if not args["auth_subject"]:
            args["auth_subject"] = input("Enter the admin email for domain-wide delegation: ")

        # Generate the auth conf
        auth_s = genconfstring(args, docstring_params, "auth", "auth_")
        encryption_pw = None
        if not args["insecure"]:
            encryption_pw = getpass.getpass("Please create a password for file encryption: ")
        write_auth(outpath_auth, auth_s, logger=logger, encryption_pw=encryption_pw, insecure=args["insecure"])
        logger.debug("auth config created")
    else:
        logger.debug("Auth file already exists")

    if not new:
        old_config = configparser.ConfigParser()
        old_config.read('.conf')
        old_dict_config = old_config._sections
        # merge in dict_config from parameters
        for key in old_dict_config.keys():
            if key in dict_config:
                old_dict_config[key].update(dict_config[key])
        dict_config = old_dict_config

    # Generate the main config
    conf_s = genconfstring(args, docstring_params, "config", "config_", dict_config)
    conf_s += genconfstring(args, docstring_params, "filters", "filters_", dict_config)

    dumpers = {"directory": GoogleDirectoryDumper,
               "gmail": GmailDumper,
               "gcp": GCPDataDumper,
               "alerts": AlertCenterDumper}
    # Go through each data dumper and generate the config values for each dump method
    for section_name, section_func in dumpers.items():
        func_args = {}
        dumper_docstrings = {}
        for func_name in [x for x in dir(section_func) if x.startswith('dump_')]:
            func_args[func_name] = args[section_name]
            docs = parse(section_func.__dict__[func_name].__doc__)
            if docs.short_description:
                dumper_docstrings[func_name] = docs.short_description
        conf_s += genconfstring(func_args, dumper_docstrings, section_name, "dump_", dict_config)

    with open(outpath_conf, 'w') as f:
        f.write(conf_s)

if __name__ == "__main__":
    fire.Fire(genconf)
