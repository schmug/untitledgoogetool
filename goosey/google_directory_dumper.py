#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""Untitled Goose Tool: google_directory_dumper!
This module has all the telemetry pulls for Google Workspace Directory and Reports.
Replaces the Entra ID data dumper with Google Admin SDK Directory API and Reports API.
"""

import asyncio
import json
import os

from datetime import datetime, timedelta
from googleapiclient.discovery import build
from goosey.datadumper import DataDumper
from goosey.utils import *

class GoogleDirectoryDumper(DataDumper):

    def __init__(self, output_dir, reports_dir, credentials, session, config, debug):
        super().__init__(f'{output_dir}{os.path.sep}directory', reports_dir, {}, session, debug)
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

        # Build Google API services
        self.directory_service = build('admin', 'directory_v1', credentials=self.credentials)
        self.reports_service = build('admin', 'reports_v1', credentials=self.credentials)

    async def dump_users(self) -> None:
        """
        Dump all users in the Google Workspace domain
        """
        self.logger.info('Dumping users...')
        outfile = os.path.join(self.output_dir, 'users.json')
        request = self.directory_service.users().list(
            customer=self.customer_id,
            maxResults=500,
            orderBy='email',
            projection='full'
        )
        total = await dump_google_api_results(
            self.directory_service.users(), request, outfile, self.logger, key='users'
        )
        self.logger.info(f'Finished dumping {total} users.')

    async def dump_groups(self) -> None:
        """
        Dump all groups in the Google Workspace domain
        """
        self.logger.info('Dumping groups...')
        outfile = os.path.join(self.output_dir, 'groups.json')
        request = self.directory_service.groups().list(
            customer=self.customer_id,
            maxResults=200
        )
        total = await dump_google_api_results(
            self.directory_service.groups(), request, outfile, self.logger, key='groups'
        )
        self.logger.info(f'Finished dumping {total} groups.')

    async def dump_group_members(self) -> None:
        """
        Dump members for all groups
        """
        self.logger.info('Dumping group members...')
        groups_file = os.path.join(self.output_dir, 'groups.json')
        if not os.path.isfile(groups_file):
            await self.dump_groups()

        if not os.path.isfile(groups_file):
            self.logger.warning('No groups file found. Skipping group members.')
            return

        outfile = os.path.join(self.output_dir, 'group_members.json')
        groups = [json.loads(line) for line in open(groups_file, 'r')]

        for group in groups:
            group_key = group.get('id', group.get('email', ''))
            try:
                request = self.directory_service.members().list(groupKey=group_key, maxResults=200)
                response = request.execute()
                members = response.get('members', [])
                for member in members:
                    member['groupId'] = group_key
                    member['groupEmail'] = group.get('email', '')
                with open(outfile, 'a+', encoding='utf-8') as f:
                    for member in members:
                        f.write(json.dumps(member) + '\n')

                # Handle pagination
                while 'nextPageToken' in response:
                    request = self.directory_service.members().list(
                        groupKey=group_key, maxResults=200,
                        pageToken=response['nextPageToken']
                    )
                    response = request.execute()
                    members = response.get('members', [])
                    for member in members:
                        member['groupId'] = group_key
                        member['groupEmail'] = group.get('email', '')
                    with open(outfile, 'a+', encoding='utf-8') as f:
                        for member in members:
                            f.write(json.dumps(member) + '\n')

            except Exception as e:
                self.logger.debug(f'Error getting members for group {group_key}: {str(e)}')

        self.logger.info('Finished dumping group members.')

    async def dump_org_units(self) -> None:
        """
        Dump organizational units
        """
        self.logger.info('Dumping organizational units...')
        outfile = os.path.join(self.output_dir, 'org_units.json')
        try:
            response = self.directory_service.orgunits().list(
                customerId=self.customer_id, type='all'
            ).execute()
            org_units = response.get('organizationUnits', [])
            with open(outfile, 'w', encoding='utf-8') as f:
                for ou in org_units:
                    f.write(json.dumps(ou) + '\n')
            self.logger.info(f'Dumped {len(org_units)} organizational units.')
        except Exception as e:
            self.logger.error(f'Error dumping org units: {str(e)}')

    async def dump_roles(self) -> None:
        """
        Dump admin roles
        """
        self.logger.info('Dumping admin roles...')
        outfile = os.path.join(self.output_dir, 'roles.json')
        try:
            response = self.directory_service.roles().list(
                customer=self.customer_id
            ).execute()
            roles = response.get('items', [])
            with open(outfile, 'w', encoding='utf-8') as f:
                for role in roles:
                    f.write(json.dumps(role) + '\n')
            self.logger.info(f'Dumped {len(roles)} admin roles.')
        except Exception as e:
            self.logger.error(f'Error dumping roles: {str(e)}')

    async def dump_role_assignments(self) -> None:
        """
        Dump admin role assignments
        """
        self.logger.info('Dumping admin role assignments...')
        outfile = os.path.join(self.output_dir, 'role_assignments.json')
        request = self.directory_service.roleAssignments().list(
            customer=self.customer_id,
            maxResults=200
        )
        total = await dump_google_api_results(
            self.directory_service.roleAssignments(), request, outfile, self.logger, key='items'
        )
        self.logger.info(f'Finished dumping {total} role assignments.')

    async def dump_domains(self) -> None:
        """
        Dump domains associated with the account
        """
        self.logger.info('Dumping domains...')
        outfile = os.path.join(self.output_dir, 'domains.json')
        try:
            response = self.directory_service.domains().list(
                customer=self.customer_id
            ).execute()
            domains = response.get('domains', [])
            with open(outfile, 'w', encoding='utf-8') as f:
                for domain in domains:
                    f.write(json.dumps(domain) + '\n')
            self.logger.info(f'Dumped {len(domains)} domains.')
        except Exception as e:
            self.logger.error(f'Error dumping domains: {str(e)}')

    async def dump_chromeos_devices(self) -> None:
        """
        Dump ChromeOS devices
        """
        self.logger.info('Dumping ChromeOS devices...')
        outfile = os.path.join(self.output_dir, 'chromeos_devices.json')
        request = self.directory_service.chromeosdevices().list(
            customerId=self.customer_id,
            maxResults=200,
            projection='FULL'
        )
        total = await dump_google_api_results(
            self.directory_service.chromeosdevices(), request, outfile, self.logger, key='chromeosdevices'
        )
        self.logger.info(f'Finished dumping {total} ChromeOS devices.')

    async def dump_mobile_devices(self) -> None:
        """
        Dump mobile devices
        """
        self.logger.info('Dumping mobile devices...')
        outfile = os.path.join(self.output_dir, 'mobile_devices.json')
        request = self.directory_service.mobiledevices().list(
            customerId=self.customer_id,
            maxResults=200
        )
        total = await dump_google_api_results(
            self.directory_service.mobiledevices(), request, outfile, self.logger, key='mobiledevices'
        )
        self.logger.info(f'Finished dumping {total} mobile devices.')

    async def dump_tokens(self) -> None:
        """
        Dump OAuth tokens for all users (third-party app access)
        """
        self.logger.info('Dumping user tokens (third-party app access)...')
        users_file = os.path.join(self.output_dir, 'users.json')
        if not os.path.isfile(users_file):
            await self.dump_users()

        if not os.path.isfile(users_file):
            self.logger.warning('No users file found. Skipping tokens.')
            return

        outfile = os.path.join(self.output_dir, 'tokens.json')
        users = [json.loads(line) for line in open(users_file, 'r')]

        for user in users:
            user_key = user.get('primaryEmail', user.get('id', ''))
            try:
                response = self.directory_service.tokens().list(userKey=user_key).execute()
                tokens = response.get('items', [])
                if tokens:
                    with open(outfile, 'a+', encoding='utf-8') as f:
                        for token in tokens:
                            token['userEmail'] = user_key
                            f.write(json.dumps(token) + '\n')
            except Exception as e:
                self.logger.debug(f'Error getting tokens for {user_key}: {str(e)}')
                await asyncio.sleep(0)

        self.logger.info('Finished dumping user tokens.')

    async def dump_login_activity(self) -> None:
        """
        Dump login/sign-in audit logs from the Reports API
        """
        self.logger.info('Dumping login activity logs...')

        sub_dir = os.path.join(self.output_dir, 'login_activity')
        check_output_dir(sub_dir, self.logger)

        if self.date_range:
            start = self.date_start + 'T00:00:00.000Z'
            end_date = self.date_end + 'T23:59:59.000Z'
        else:
            start = (datetime.now() - timedelta(days=180)).strftime("%Y-%m-%dT00:00:00.000Z")
            end_date = datetime.now().strftime("%Y-%m-%dT23:59:59.000Z")

        statefile = f'{self.output_dir}{os.path.sep}.login_activity_state'
        if os.path.isfile(statefile):
            self.logger.info('Login activity save state found. Continuing from last checkpoint.')
            start = open(statefile, 'r').read().strip()

        outfile = os.path.join(sub_dir, 'login_activity.json')
        self.logger.debug(f'Pulling login activity from {start} to {end_date}')

        try:
            request = self.reports_service.activities().list(
                userKey='all',
                applicationName='login',
                startTime=start,
                endTime=end_date,
                maxResults=1000
            )
            total = await dump_google_api_results(
                self.reports_service.activities(), request, outfile, self.logger, key='items'
            )
            with open(statefile, 'w') as f:
                f.write(end_date)
            self.logger.info(f'Finished dumping {total} login activity records.')
        except Exception as e:
            self.logger.error(f'Error dumping login activity: {str(e)}')

    async def dump_admin_activity(self) -> None:
        """
        Dump admin audit logs from the Reports API
        """
        self.logger.info('Dumping admin activity logs...')

        sub_dir = os.path.join(self.output_dir, 'admin_activity')
        check_output_dir(sub_dir, self.logger)

        if self.date_range:
            start = self.date_start + 'T00:00:00.000Z'
            end_date = self.date_end + 'T23:59:59.000Z'
        else:
            start = (datetime.now() - timedelta(days=180)).strftime("%Y-%m-%dT00:00:00.000Z")
            end_date = datetime.now().strftime("%Y-%m-%dT23:59:59.000Z")

        statefile = f'{self.output_dir}{os.path.sep}.admin_activity_state'
        if os.path.isfile(statefile):
            self.logger.info('Admin activity save state found. Continuing from last checkpoint.')
            start = open(statefile, 'r').read().strip()

        outfile = os.path.join(sub_dir, 'admin_activity.json')
        self.logger.debug(f'Pulling admin activity from {start} to {end_date}')

        try:
            request = self.reports_service.activities().list(
                userKey='all',
                applicationName='admin',
                startTime=start,
                endTime=end_date,
                maxResults=1000
            )
            total = await dump_google_api_results(
                self.reports_service.activities(), request, outfile, self.logger, key='items'
            )
            with open(statefile, 'w') as f:
                f.write(end_date)
            self.logger.info(f'Finished dumping {total} admin activity records.')
        except Exception as e:
            self.logger.error(f'Error dumping admin activity: {str(e)}')

    async def dump_drive_activity(self) -> None:
        """
        Dump Google Drive audit logs from the Reports API
        """
        self.logger.info('Dumping Drive activity logs...')

        sub_dir = os.path.join(self.output_dir, 'drive_activity')
        check_output_dir(sub_dir, self.logger)

        if self.date_range:
            start = self.date_start + 'T00:00:00.000Z'
            end_date = self.date_end + 'T23:59:59.000Z'
        else:
            start = (datetime.now() - timedelta(days=180)).strftime("%Y-%m-%dT00:00:00.000Z")
            end_date = datetime.now().strftime("%Y-%m-%dT23:59:59.000Z")

        statefile = f'{self.output_dir}{os.path.sep}.drive_activity_state'
        if os.path.isfile(statefile):
            self.logger.info('Drive activity save state found. Continuing from last checkpoint.')
            start = open(statefile, 'r').read().strip()

        outfile = os.path.join(sub_dir, 'drive_activity.json')

        try:
            request = self.reports_service.activities().list(
                userKey='all',
                applicationName='drive',
                startTime=start,
                endTime=end_date,
                maxResults=1000
            )
            total = await dump_google_api_results(
                self.reports_service.activities(), request, outfile, self.logger, key='items'
            )
            with open(statefile, 'w') as f:
                f.write(end_date)
            self.logger.info(f'Finished dumping {total} Drive activity records.')
        except Exception as e:
            self.logger.error(f'Error dumping Drive activity: {str(e)}')

    async def dump_saml_activity(self) -> None:
        """
        Dump SAML audit logs from the Reports API
        """
        self.logger.info('Dumping SAML activity logs...')

        sub_dir = os.path.join(self.output_dir, 'saml_activity')
        check_output_dir(sub_dir, self.logger)

        if self.date_range:
            start = self.date_start + 'T00:00:00.000Z'
            end_date = self.date_end + 'T23:59:59.000Z'
        else:
            start = (datetime.now() - timedelta(days=180)).strftime("%Y-%m-%dT00:00:00.000Z")
            end_date = datetime.now().strftime("%Y-%m-%dT23:59:59.000Z")

        outfile = os.path.join(sub_dir, 'saml_activity.json')

        try:
            request = self.reports_service.activities().list(
                userKey='all',
                applicationName='saml',
                startTime=start,
                endTime=end_date,
                maxResults=1000
            )
            total = await dump_google_api_results(
                self.reports_service.activities(), request, outfile, self.logger, key='items'
            )
            self.logger.info(f'Finished dumping {total} SAML activity records.')
        except Exception as e:
            self.logger.error(f'Error dumping SAML activity: {str(e)}')

    async def dump_token_activity(self) -> None:
        """
        Dump OAuth token audit logs from the Reports API
        """
        self.logger.info('Dumping token activity logs...')

        sub_dir = os.path.join(self.output_dir, 'token_activity')
        check_output_dir(sub_dir, self.logger)

        if self.date_range:
            start = self.date_start + 'T00:00:00.000Z'
            end_date = self.date_end + 'T23:59:59.000Z'
        else:
            start = (datetime.now() - timedelta(days=180)).strftime("%Y-%m-%dT00:00:00.000Z")
            end_date = datetime.now().strftime("%Y-%m-%dT23:59:59.000Z")

        outfile = os.path.join(sub_dir, 'token_activity.json')

        try:
            request = self.reports_service.activities().list(
                userKey='all',
                applicationName='token',
                startTime=start,
                endTime=end_date,
                maxResults=1000
            )
            total = await dump_google_api_results(
                self.reports_service.activities(), request, outfile, self.logger, key='items'
            )
            self.logger.info(f'Finished dumping {total} token activity records.')
        except Exception as e:
            self.logger.error(f'Error dumping token activity: {str(e)}')

    async def dump_user_usage(self) -> None:
        """
        Dump user usage reports from the Reports API
        """
        self.logger.info('Dumping user usage reports...')
        outfile = os.path.join(self.output_dir, 'user_usage_report.json')

        # Usage reports need a specific date (not range), use yesterday
        report_date = (datetime.now() - timedelta(days=2)).strftime("%Y-%m-%d")

        try:
            request = self.reports_service.userUsageReport().get(
                userKey='all',
                date=report_date,
                maxResults=1000
            )
            total = await dump_google_api_results(
                self.reports_service.userUsageReport(), request, outfile, self.logger, key='usageReports'
            )
            self.logger.info(f'Finished dumping {total} user usage reports.')
        except Exception as e:
            self.logger.error(f'Error dumping user usage reports: {str(e)}')

    async def dump_customer_usage(self) -> None:
        """
        Dump customer usage reports from the Reports API
        """
        self.logger.info('Dumping customer usage reports...')
        outfile = os.path.join(self.output_dir, 'customer_usage_report.json')

        report_date = (datetime.now() - timedelta(days=2)).strftime("%Y-%m-%d")

        try:
            response = self.reports_service.customerUsageReports().get(
                date=report_date
            ).execute()
            usage_reports = response.get('usageReports', [])
            with open(outfile, 'w', encoding='utf-8') as f:
                for report in usage_reports:
                    f.write(json.dumps(report) + '\n')
            self.logger.info(f'Dumped {len(usage_reports)} customer usage reports.')
        except Exception as e:
            self.logger.error(f'Error dumping customer usage reports: {str(e)}')
