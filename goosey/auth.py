#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""Untitled Goose Tool: Auth!
This module handles authentication to Google Workspace and GCP environments.
"""

import configparser
import copy
import getpass
import io
import json
import os
import sys
import time

from google.oauth2 import service_account
from google.auth.transport.requests import Request
from goosey.utils import *

green = "\x1b[1;32m"
bold_red = "\x1b[31;1m"

# Scopes needed for Google Workspace data collection
GOOGLE_WORKSPACE_SCOPES = [
    'https://www.googleapis.com/auth/admin.directory.user.readonly',
    'https://www.googleapis.com/auth/admin.directory.group.readonly',
    'https://www.googleapis.com/auth/admin.directory.device.chromeos.readonly',
    'https://www.googleapis.com/auth/admin.directory.device.mobile.readonly',
    'https://www.googleapis.com/auth/admin.directory.domain.readonly',
    'https://www.googleapis.com/auth/admin.directory.rolemanagement.readonly',
    'https://www.googleapis.com/auth/admin.directory.orgunit.readonly',
    'https://www.googleapis.com/auth/admin.directory.customer.readonly',
    'https://www.googleapis.com/auth/admin.reports.audit.readonly',
    'https://www.googleapis.com/auth/admin.reports.usage.readonly',
    'https://www.googleapis.com/auth/gmail.readonly',
    'https://www.googleapis.com/auth/gmail.settings.basic',
    'https://www.googleapis.com/auth/apps.alerts',
]

GCP_SCOPES = [
    'https://www.googleapis.com/auth/cloud-platform.read-only',
    'https://www.googleapis.com/auth/compute.readonly',
    'https://www.googleapis.com/auth/logging.read',
]


class Authentication():
    """
    Authentication class for Untitled Goose Tool (Google Workspace edition)
    """
    def __init__(self, debug=False):
        self.tokendata = {}
        self.logger = None
        self.encryption_pw = None

    def authenticate_as_service_account(self):
        """
        Authenticate using a Google service account JSON key file with domain-wide delegation.
        """
        try:
            all_scopes = GOOGLE_WORKSPACE_SCOPES + GCP_SCOPES
            credentials = service_account.Credentials.from_service_account_file(
                self.service_account_file,
                scopes=all_scopes
            )

            # If a subject (admin user) is specified, use domain-wide delegation
            if self.subject:
                credentials = credentials.with_subject(self.subject)

            # Force a token refresh to validate credentials
            credentials.refresh(Request())

            self.tokendata = {
                'token': credentials.token,
                'expiry': credentials.expiry.isoformat() if credentials.expiry else None,
                'service_account_email': credentials.service_account_email,
                'project_id': credentials._project_id if hasattr(credentials, '_project_id') else None,
                'subject': self.subject,
                'service_account_file': self.service_account_file,
                'scopes': all_scopes,
            }

            self.logger.info(green + "Google Workspace authentication complete." + green)
            return self.tokendata

        except Exception as e:
            self.logger.error(f"Error authenticating with service account: {str(e)}")
            sys.exit(1)

    def get_credentials(self):
        """
        Build and return refreshable credentials from stored auth info.
        """
        all_scopes = GOOGLE_WORKSPACE_SCOPES + GCP_SCOPES
        credentials = service_account.Credentials.from_service_account_file(
            self.service_account_file,
            scopes=all_scopes
        )
        if self.subject:
            credentials = credentials.with_subject(self.subject)
        credentials.refresh(Request())
        return credentials

    def parse_config(self, configfile):
        config = configparser.ConfigParser()
        config.read(configfile)
        self.customer_id = config_get(config, 'config', 'customer_id', self.logger)
        self.domain = config_get(config, 'config', 'domain', self.logger)
        self.gcp_projects = config_get(config, 'config', 'gcp_projects', self.logger)
        return config

    def parse_auth(self, authstr=None):
        self.authconfig = configparser.ConfigParser()
        auth_dict = {}
        if authstr:
            self.authconfig.read_string(authstr)

        # Service account key file path
        if config_get(self.authconfig, 'auth', 'service_account_file', self.logger):
            self.service_account_file = config_get(self.authconfig, 'auth', 'service_account_file', self.logger)
        else:
            self.service_account_file = input("Please enter the path to your service account JSON key file: ")
        auth_dict["service_account_file"] = self.service_account_file

        # Subject (admin user email for domain-wide delegation)
        if config_get(self.authconfig, 'auth', 'subject', self.logger):
            self.subject = config_get(self.authconfig, 'auth', 'subject', self.logger)
        else:
            self.subject = input("Please enter the admin email for domain-wide delegation: ")
        auth_dict["subject"] = self.subject

        self.authconfig["auth"] = auth_dict

    def _read_current_tokens(self, filepath: str):
        tokens = {}
        tokens_str = read_auth(filepath, logger=self.logger, encryption_pw=self.encryption_pw)
        if tokens_str:
            tokens = json.loads(tokens_str)
        return tokens

    def _write_current_tokens(self, filepath: str, tokens: dict):
        writestr = json.dumps(tokens, indent=2, sort_keys=True)
        write_auth(filepath, writestr, logger=self.logger, encryption_pw=self.encryption_pw, insecure=self.insecure)

    def ugt_auth(self):
        custom_auth_dict = self._read_current_tokens(self.authfile)
        self._write_current_tokens(self.authfile, custom_auth_dict)

        if 'google_auth' not in custom_auth_dict:
            custom_auth_dict['google_auth'] = {}

        custom_auth_dict['google_auth']['service_account_file'] = self.service_account_file
        custom_auth_dict['google_auth']['subject'] = self.subject

        try:
            self.authenticate_as_service_account()
            if self.tokendata:
                custom_auth_dict['google_auth'].update(copy.copy(self.tokendata))
        except Exception as e:
            self.logger.error(f"Error authenticating: {str(e)}")

        self._write_current_tokens(self.authfile, custom_auth_dict)

    def parse_args(self, args):
        self.debug = args.debug
        self.logger = setup_logger(__name__, self.debug)
        self.authfile = args.authfile
        self.auth = args.auth
        self.insecure = args.insecure
        self.encryption_pw = args.encryption_pw
        self.config = args.config

        if not self.insecure:
            if self.encryption_pw is None:
                self.encryption_pw = getpass.getpass("Please type the password for file encryption: ")
        auth_config_str = read_auth(self.auth, logger=self.logger, encryption_pw=self.encryption_pw)

        # Read in authconfig or prompt for user info
        self.parse_auth(auth_config_str)

        authio = io.StringIO()
        self.authconfig.write(authio)
        authio.seek(0)
        auth_config_str = authio.getvalue()

        write_auth(self.auth, auth_config_str, logger=self.logger, encryption_pw=self.encryption_pw, insecure=self.insecure)

        self.parse_config(self.config)


def check_google_auth(auth_data, logger):
    """Check if we have valid auth data with a service account file."""
    if 'service_account_file' not in auth_data:
        logger.warning("Missing service account file in auth data. Please re-authenticate.")
        sys.exit(1)
    if not os.path.isfile(auth_data['service_account_file']):
        logger.warning(f"Service account file not found: {auth_data['service_account_file']}")
        sys.exit(1)
    return False


def get_google_credentials(auth_data, scopes=None, subject=None):
    """
    Build Google credentials from stored auth data.

    Args:
        auth_data: Dict containing service_account_file and subject
        scopes: Optional list of scopes (defaults to all workspace + GCP scopes)
        subject: Optional override for domain-wide delegation subject
    """
    if scopes is None:
        scopes = GOOGLE_WORKSPACE_SCOPES + GCP_SCOPES

    sa_file = auth_data.get('service_account_file', '')
    delegated_user = subject or auth_data.get('subject', '')

    credentials = service_account.Credentials.from_service_account_file(
        sa_file, scopes=scopes
    )
    if delegated_user:
        credentials = credentials.with_subject(delegated_user)

    credentials.refresh(Request())
    return credentials


def auth(authfile=".ugt_auth",
         config=".conf",
         auth=".auth",
         debug=False,
         insecure=False,
         encryption_pw=None):
    """
    Untitled Goose Tool Authentication (Google Workspace)

    Args:
        authfile: File to store the authentication tokens
        config: Path to config file
        auth: File to store the credentials used for authentication
        debug: Enable debug logging
        insecure: Disable secure authentication handling (file encryption)
        encryption_pw: password used for auth file encryption. SHOULD ONLY BE USED WITH AUTOHONK
    """
    args = dict2obj(locals())
    a = Authentication(debug=debug)
    a.parse_args(args)
    a.ugt_auth()

if __name__ == '__main__':
    main()
