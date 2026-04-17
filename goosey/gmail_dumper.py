#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""Untitled Goose Tool: gmail_dumper!
This module has all the telemetry pulls for Gmail settings and configuration.
Replaces the M365 data dumper with Gmail API calls.
"""

import asyncio
import json
import os

from datetime import datetime, timedelta
from google.oauth2 import service_account
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from goosey.datadumper import DataDumper
from goosey.utils import *

# Gmail-specific scopes
GMAIL_SCOPES = [
    'https://www.googleapis.com/auth/gmail.readonly',
    'https://www.googleapis.com/auth/gmail.settings.basic',
]

class GmailDumper(DataDumper):

    def __init__(self, output_dir, reports_dir, credentials, session, config, debug):
        super().__init__(f'{output_dir}{os.path.sep}gmail', reports_dir, {}, session, debug)
        self.logger = setup_logger(__name__, debug)
        self.credentials = credentials
        self.failurefile = os.path.join(reports_dir, '_no_results.json')

        self.customer_id = config_get(config, 'config', 'customer_id', self.logger) or 'my_customer'
        self.domain = config_get(config, 'config', 'domain', self.logger)

        filters = config_get(config, 'filters', 'date_start', logger=self.logger)
        if filters != '' and filters is not None:
            self.date_range = True
            self.date_start = config_get(config, 'filters', 'date_start')
            if config_get(config, 'filters', 'date_end') != '':
                self.date_end = config_get(config, 'filters', 'date_end')
            else:
                self.date_end = datetime.now().strftime("%Y-%m-%d")
        else:
            self.date_range = False

        # Build directory service to get user list
        self.directory_service = build('admin', 'directory_v1', credentials=self.credentials)
        # Store the base credentials (service account) for per-user delegation
        self.sa_credentials = credentials

    def _get_gmail_service_for_user(self, user_email):
        """
        Build a Gmail service delegated to a specific user.
        """
        delegated_credentials = self.sa_credentials.with_subject(user_email)
        delegated_credentials.refresh(Request())
        return build('gmail', 'v1', credentials=delegated_credentials)

    async def _get_all_users(self):
        """Get all user emails from the directory."""
        users_file = os.path.join(os.path.dirname(self.output_dir), 'directory', 'users.json')
        if os.path.isfile(users_file):
            return [json.loads(line).get('primaryEmail', '') for line in open(users_file, 'r') if line.strip()]

        # Fall back to fetching users directly
        users = []
        request = self.directory_service.users().list(
            customer=self.customer_id,
            maxResults=500,
            projection='basic'
        )
        while request is not None:
            try:
                response = request.execute()
                for user in response.get('users', []):
                    users.append(user.get('primaryEmail', ''))
                request = self.directory_service.users().list_next(request, response)
            except Exception as e:
                self.logger.error(f'Error fetching users: {str(e)}')
                break
        return users

    async def dump_filters(self) -> None:
        """
        Dump Gmail filters/rules for all users
        """
        self.logger.info('Dumping Gmail filters for all users...')
        outfile = os.path.join(self.output_dir, 'gmail_filters.json')
        users = await self._get_all_users()

        statefile = f'{self.output_dir}{os.path.sep}.filters_state'
        start_idx = 0
        if os.path.isfile(statefile):
            start_idx = int(open(statefile, 'r').read().strip())
            self.logger.info(f'Filters save state found. Starting from user index {start_idx}.')

        for i in range(start_idx, len(users)):
            user_email = users[i]
            try:
                gmail = self._get_gmail_service_for_user(user_email)
                response = gmail.users().settings().filters().list(userId='me').execute()
                filters = response.get('filter', [])
                if filters:
                    with open(outfile, 'a+', encoding='utf-8') as f:
                        for filt in filters:
                            filt['userEmail'] = user_email
                            f.write(json.dumps(filt) + '\n')
                with open(statefile, 'w') as f:
                    f.write(str(i))
            except Exception as e:
                self.logger.debug(f'Error getting filters for {user_email}: {str(e)}')
            await asyncio.sleep(0)

        self.logger.info('Finished dumping Gmail filters.')

    async def dump_forwarding(self) -> None:
        """
        Dump Gmail forwarding addresses for all users
        """
        self.logger.info('Dumping Gmail forwarding addresses for all users...')
        outfile = os.path.join(self.output_dir, 'gmail_forwarding.json')
        users = await self._get_all_users()

        statefile = f'{self.output_dir}{os.path.sep}.forwarding_state'
        start_idx = 0
        if os.path.isfile(statefile):
            start_idx = int(open(statefile, 'r').read().strip())

        for i in range(start_idx, len(users)):
            user_email = users[i]
            try:
                gmail = self._get_gmail_service_for_user(user_email)
                response = gmail.users().settings().forwardingAddresses().list(userId='me').execute()
                addresses = response.get('forwardingAddresses', [])
                if addresses:
                    with open(outfile, 'a+', encoding='utf-8') as f:
                        for addr in addresses:
                            addr['userEmail'] = user_email
                            f.write(json.dumps(addr) + '\n')
                with open(statefile, 'w') as f:
                    f.write(str(i))
            except Exception as e:
                self.logger.debug(f'Error getting forwarding for {user_email}: {str(e)}')
            await asyncio.sleep(0)

        self.logger.info('Finished dumping Gmail forwarding addresses.')

    async def dump_delegates(self) -> None:
        """
        Dump Gmail delegates for all users
        """
        self.logger.info('Dumping Gmail delegates for all users...')
        outfile = os.path.join(self.output_dir, 'gmail_delegates.json')
        users = await self._get_all_users()

        statefile = f'{self.output_dir}{os.path.sep}.delegates_state'
        start_idx = 0
        if os.path.isfile(statefile):
            start_idx = int(open(statefile, 'r').read().strip())

        for i in range(start_idx, len(users)):
            user_email = users[i]
            try:
                gmail = self._get_gmail_service_for_user(user_email)
                response = gmail.users().settings().delegates().list(userId='me').execute()
                delegates = response.get('delegates', [])
                if delegates:
                    with open(outfile, 'a+', encoding='utf-8') as f:
                        for delegate in delegates:
                            delegate['userEmail'] = user_email
                            f.write(json.dumps(delegate) + '\n')
                with open(statefile, 'w') as f:
                    f.write(str(i))
            except Exception as e:
                self.logger.debug(f'Error getting delegates for {user_email}: {str(e)}')
            await asyncio.sleep(0)

        self.logger.info('Finished dumping Gmail delegates.')

    async def dump_send_as(self) -> None:
        """
        Dump Gmail send-as aliases for all users
        """
        self.logger.info('Dumping Gmail send-as aliases for all users...')
        outfile = os.path.join(self.output_dir, 'gmail_send_as.json')
        users = await self._get_all_users()

        statefile = f'{self.output_dir}{os.path.sep}.send_as_state'
        start_idx = 0
        if os.path.isfile(statefile):
            start_idx = int(open(statefile, 'r').read().strip())

        for i in range(start_idx, len(users)):
            user_email = users[i]
            try:
                gmail = self._get_gmail_service_for_user(user_email)
                response = gmail.users().settings().sendAs().list(userId='me').execute()
                send_as_list = response.get('sendAs', [])
                if send_as_list:
                    with open(outfile, 'a+', encoding='utf-8') as f:
                        for sa in send_as_list:
                            sa['userEmail'] = user_email
                            f.write(json.dumps(sa) + '\n')
                with open(statefile, 'w') as f:
                    f.write(str(i))
            except Exception as e:
                self.logger.debug(f'Error getting send-as for {user_email}: {str(e)}')
            await asyncio.sleep(0)

        self.logger.info('Finished dumping Gmail send-as aliases.')

    async def dump_auto_forwarding(self) -> None:
        """
        Dump Gmail auto-forwarding settings for all users
        """
        self.logger.info('Dumping Gmail auto-forwarding settings for all users...')
        outfile = os.path.join(self.output_dir, 'gmail_auto_forwarding.json')
        users = await self._get_all_users()

        for user_email in users:
            try:
                gmail = self._get_gmail_service_for_user(user_email)
                response = gmail.users().settings().getAutoForwarding(userId='me').execute()
                response['userEmail'] = user_email
                with open(outfile, 'a+', encoding='utf-8') as f:
                    f.write(json.dumps(response) + '\n')
            except Exception as e:
                self.logger.debug(f'Error getting auto-forwarding for {user_email}: {str(e)}')
            await asyncio.sleep(0)

        self.logger.info('Finished dumping Gmail auto-forwarding settings.')

    async def dump_imap_settings(self) -> None:
        """
        Dump Gmail IMAP settings for all users
        """
        self.logger.info('Dumping Gmail IMAP settings for all users...')
        outfile = os.path.join(self.output_dir, 'gmail_imap_settings.json')
        users = await self._get_all_users()

        for user_email in users:
            try:
                gmail = self._get_gmail_service_for_user(user_email)
                response = gmail.users().settings().getImap(userId='me').execute()
                response['userEmail'] = user_email
                with open(outfile, 'a+', encoding='utf-8') as f:
                    f.write(json.dumps(response) + '\n')
            except Exception as e:
                self.logger.debug(f'Error getting IMAP settings for {user_email}: {str(e)}')
            await asyncio.sleep(0)

        self.logger.info('Finished dumping Gmail IMAP settings.')

    async def dump_pop_settings(self) -> None:
        """
        Dump Gmail POP settings for all users
        """
        self.logger.info('Dumping Gmail POP settings for all users...')
        outfile = os.path.join(self.output_dir, 'gmail_pop_settings.json')
        users = await self._get_all_users()

        for user_email in users:
            try:
                gmail = self._get_gmail_service_for_user(user_email)
                response = gmail.users().settings().getPop(userId='me').execute()
                response['userEmail'] = user_email
                with open(outfile, 'a+', encoding='utf-8') as f:
                    f.write(json.dumps(response) + '\n')
            except Exception as e:
                self.logger.debug(f'Error getting POP settings for {user_email}: {str(e)}')
            await asyncio.sleep(0)

        self.logger.info('Finished dumping Gmail POP settings.')

    async def dump_vacation_settings(self) -> None:
        """
        Dump Gmail vacation/out-of-office settings for all users
        """
        self.logger.info('Dumping Gmail vacation settings for all users...')
        outfile = os.path.join(self.output_dir, 'gmail_vacation_settings.json')
        users = await self._get_all_users()

        for user_email in users:
            try:
                gmail = self._get_gmail_service_for_user(user_email)
                response = gmail.users().settings().getVacation(userId='me').execute()
                response['userEmail'] = user_email
                with open(outfile, 'a+', encoding='utf-8') as f:
                    f.write(json.dumps(response) + '\n')
            except Exception as e:
                self.logger.debug(f'Error getting vacation settings for {user_email}: {str(e)}')
            await asyncio.sleep(0)

        self.logger.info('Finished dumping Gmail vacation settings.')
