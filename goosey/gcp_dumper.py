#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""Untitled Goose Tool: gcp_dumper!
This module has all the telemetry pulls for Google Cloud Platform resources.
Replaces the Azure data dumper with GCP API calls.
"""

import asyncio
import json
import os
import pytz

from datetime import datetime, timedelta
from googleapiclient.discovery import build
from goosey.datadumper import DataDumper
from goosey.utils import *

utc = pytz.UTC

class GCPDataDumper(DataDumper):

    def __init__(self, output_dir, reports_dir, credentials, session, config, debug):
        super().__init__(f'{output_dir}{os.path.sep}gcp', reports_dir, {}, session, debug)
        self.logger = setup_logger(__name__, debug)
        self.credentials = credentials
        self.failurefile = os.path.join(reports_dir, '_no_results.json')

        # Get GCP project IDs from config
        gcp_projects_str = config_get(config, 'config', 'gcp_projects', self.logger) or ''
        if gcp_projects_str.lower() == 'all' or gcp_projects_str == '':
            self.project_ids = []  # Will be populated by listing projects
        else:
            self.project_ids = [p.strip() for p in gcp_projects_str.split(',')]

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

        # Build GCP services
        self.crm_service = build('cloudresourcemanager', 'v1', credentials=self.credentials)
        self.compute_service = build('compute', 'v1', credentials=self.credentials)
        self.iam_service = build('iam', 'v1', credentials=self.credentials)
        self.logging_service = build('logging', 'v2', credentials=self.credentials)

    async def _get_projects(self):
        """Get all accessible GCP projects."""
        if self.project_ids:
            return self.project_ids

        projects = []
        try:
            request = self.crm_service.projects().list()
            while request is not None:
                response = request.execute()
                for project in response.get('projects', []):
                    if project.get('lifecycleState') == 'ACTIVE':
                        projects.append(project['projectId'])
                request = self.crm_service.projects().list_next(request, response)
        except Exception as e:
            self.logger.error(f'Error listing projects: {str(e)}')

        self.project_ids = projects
        return projects

    async def dump_projects(self) -> None:
        """
        Dump all accessible GCP projects
        """
        self.logger.info('Dumping GCP projects...')
        outfile = os.path.join(self.output_dir, 'projects.json')

        try:
            request = self.crm_service.projects().list()
            total = await dump_google_api_results(
                self.crm_service.projects(), request, outfile, self.logger, key='projects'
            )
            self.logger.info(f'Finished dumping {total} GCP projects.')
        except Exception as e:
            self.logger.error(f'Error dumping projects: {str(e)}')

    async def dump_iam_policies(self) -> None:
        """
        Dump IAM policies for all projects
        """
        self.logger.info('Dumping IAM policies...')
        projects = await self._get_projects()

        for project_id in projects:
            outfile = os.path.join(self.output_dir, f'iam_policy_{project_id}.json')
            if os.path.exists(outfile):
                self.logger.debug(f'IAM policy file for {project_id} exists. Skipping.')
                continue
            try:
                response = self.crm_service.projects().getIamPolicy(
                    resource=project_id, body={}
                ).execute()
                with open(outfile, 'w', encoding='utf-8') as f:
                    f.write(json.dumps(response) + '\n')
                self.logger.debug(f'Dumped IAM policy for project {project_id}.')
            except Exception as e:
                self.logger.error(f'Error getting IAM policy for {project_id}: {str(e)}')
            await asyncio.sleep(0)

        self.logger.info('Finished dumping IAM policies.')

    async def dump_service_accounts(self) -> None:
        """
        Dump service accounts for all projects
        """
        self.logger.info('Dumping service accounts...')
        projects = await self._get_projects()

        for project_id in projects:
            outfile = os.path.join(self.output_dir, f'service_accounts_{project_id}.json')
            if os.path.exists(outfile):
                self.logger.debug(f'Service accounts file for {project_id} exists. Skipping.')
                continue
            try:
                name = f'projects/{project_id}'
                response = self.iam_service.projects().serviceAccounts().list(
                    name=name
                ).execute()
                accounts = response.get('accounts', [])
                with open(outfile, 'w', encoding='utf-8') as f:
                    for acct in accounts:
                        f.write(json.dumps(acct) + '\n')
                self.logger.debug(f'Dumped {len(accounts)} service accounts for {project_id}.')
            except Exception as e:
                self.logger.error(f'Error getting service accounts for {project_id}: {str(e)}')
            await asyncio.sleep(0)

        self.logger.info('Finished dumping service accounts.')

    async def dump_service_account_keys(self) -> None:
        """
        Dump service account keys for all service accounts across all projects
        """
        self.logger.info('Dumping service account keys...')
        projects = await self._get_projects()
        outfile = os.path.join(self.output_dir, 'service_account_keys.json')

        for project_id in projects:
            sa_file = os.path.join(self.output_dir, f'service_accounts_{project_id}.json')
            if not os.path.isfile(sa_file):
                continue

            service_accounts = [json.loads(line) for line in open(sa_file, 'r') if line.strip()]
            for sa in service_accounts:
                sa_email = sa.get('email', '')
                try:
                    name = f'projects/{project_id}/serviceAccounts/{sa_email}'
                    response = self.iam_service.projects().serviceAccounts().keys().list(
                        name=name
                    ).execute()
                    keys = response.get('keys', [])
                    with open(outfile, 'a+', encoding='utf-8') as f:
                        for key in keys:
                            key['serviceAccountEmail'] = sa_email
                            key['projectId'] = project_id
                            f.write(json.dumps(key) + '\n')
                except Exception as e:
                    self.logger.debug(f'Error getting keys for {sa_email}: {str(e)}')
                await asyncio.sleep(0)

        self.logger.info('Finished dumping service account keys.')

    async def dump_compute_instances(self) -> None:
        """
        Dump all Compute Engine instances across all projects
        """
        self.logger.info('Dumping Compute Engine instances...')
        projects = await self._get_projects()

        for project_id in projects:
            outfile = os.path.join(self.output_dir, f'compute_instances_{project_id}.json')
            if os.path.exists(outfile):
                self.logger.debug(f'Compute instances file for {project_id} exists. Skipping.')
                continue
            try:
                request = self.compute_service.instances().aggregatedList(project=project_id)
                while request is not None:
                    response = request.execute()
                    for zone, zone_data in response.get('items', {}).items():
                        instances = zone_data.get('instances', [])
                        if instances:
                            with open(outfile, 'a+', encoding='utf-8') as f:
                                for instance in instances:
                                    instance['projectId'] = project_id
                                    f.write(json.dumps(instance) + '\n')
                    request = self.compute_service.instances().aggregatedList_next(request, response)
            except Exception as e:
                self.logger.error(f'Error listing instances for {project_id}: {str(e)}')
            await asyncio.sleep(0)

        self.logger.info('Finished dumping Compute Engine instances.')

    async def dump_compute_firewalls(self) -> None:
        """
        Dump all firewall rules across all projects
        """
        self.logger.info('Dumping firewall rules...')
        projects = await self._get_projects()

        for project_id in projects:
            outfile = os.path.join(self.output_dir, f'firewalls_{project_id}.json')
            if os.path.exists(outfile):
                self.logger.debug(f'Firewalls file for {project_id} exists. Skipping.')
                continue
            try:
                request = self.compute_service.firewalls().list(project=project_id)
                total = await dump_google_api_results(
                    self.compute_service.firewalls(), request, outfile, self.logger, key='items'
                )
                self.logger.debug(f'Dumped {total} firewall rules for {project_id}.')
            except Exception as e:
                self.logger.error(f'Error listing firewalls for {project_id}: {str(e)}')
            await asyncio.sleep(0)

        self.logger.info('Finished dumping firewall rules.')

    async def dump_compute_networks(self) -> None:
        """
        Dump all VPC networks across all projects
        """
        self.logger.info('Dumping VPC networks...')
        projects = await self._get_projects()

        for project_id in projects:
            outfile = os.path.join(self.output_dir, f'networks_{project_id}.json')
            if os.path.exists(outfile):
                continue
            try:
                request = self.compute_service.networks().list(project=project_id)
                total = await dump_google_api_results(
                    self.compute_service.networks(), request, outfile, self.logger, key='items'
                )
                self.logger.debug(f'Dumped {total} networks for {project_id}.')
            except Exception as e:
                self.logger.error(f'Error listing networks for {project_id}: {str(e)}')
            await asyncio.sleep(0)

        self.logger.info('Finished dumping VPC networks.')

    async def dump_storage_buckets(self) -> None:
        """
        Dump all Cloud Storage buckets across all projects
        """
        self.logger.info('Dumping Cloud Storage buckets...')
        projects = await self._get_projects()
        storage_service = build('storage', 'v1', credentials=self.credentials)

        for project_id in projects:
            outfile = os.path.join(self.output_dir, f'storage_buckets_{project_id}.json')
            if os.path.exists(outfile):
                continue
            try:
                request = storage_service.buckets().list(project=project_id)
                total = await dump_google_api_results(
                    storage_service.buckets(), request, outfile, self.logger, key='items'
                )
                self.logger.debug(f'Dumped {total} buckets for {project_id}.')
            except Exception as e:
                self.logger.error(f'Error listing buckets for {project_id}: {str(e)}')
            await asyncio.sleep(0)

        self.logger.info('Finished dumping Cloud Storage buckets.')

    async def dump_audit_logs(self) -> None:
        """
        Dump GCP audit logs (Admin Activity and Data Access) for all projects
        """
        self.logger.info('Dumping GCP audit logs...')
        projects = await self._get_projects()

        if self.date_range:
            start = self.date_start + 'T00:00:00Z'
            end_date = self.date_end + 'T23:59:59Z'
        else:
            start = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%dT00:00:00Z")
            end_date = datetime.now().strftime("%Y-%m-%dT23:59:59Z")

        log_filter = (
            f'timestamp >= "{start}" AND timestamp <= "{end_date}" AND '
            'logName:("activity" OR "data_access")'
        )

        for project_id in projects:
            outfile = os.path.join(self.output_dir, f'audit_logs_{project_id}.json')
            self.logger.debug(f'Pulling audit logs for project {project_id}...')
            try:
                body = {
                    'resourceNames': [f'projects/{project_id}'],
                    'filter': log_filter,
                    'orderBy': 'timestamp asc',
                    'pageSize': 1000
                }
                request = self.logging_service.entries().list(body=body)
                response = request.execute()
                entries = response.get('entries', [])
                if entries:
                    with open(outfile, 'a+', encoding='utf-8') as f:
                        for entry in entries:
                            f.write(json.dumps(entry) + '\n')

                while 'nextPageToken' in response:
                    body['pageToken'] = response['nextPageToken']
                    request = self.logging_service.entries().list(body=body)
                    response = request.execute()
                    entries = response.get('entries', [])
                    if entries:
                        with open(outfile, 'a+', encoding='utf-8') as f:
                            for entry in entries:
                                f.write(json.dumps(entry) + '\n')

                self.logger.debug(f'Finished audit logs for {project_id}.')
            except Exception as e:
                self.logger.error(f'Error getting audit logs for {project_id}: {str(e)}')
            await asyncio.sleep(0)

        self.logger.info('Finished dumping GCP audit logs.')
