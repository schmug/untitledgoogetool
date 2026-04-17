#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""Untitled Goose Tool: alert_center_dumper!
This module has all the telemetry pulls for Google Workspace Alert Center.
Replaces the MDE data dumper with Google Alert Center API calls.
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

class AlertCenterDumper(DataDumper):

    def __init__(self, output_dir, reports_dir, credentials, session, config, debug):
        super().__init__(f'{output_dir}{os.path.sep}alerts', reports_dir, {}, session, debug)
        self.logger = setup_logger(__name__, debug)
        self.credentials = credentials
        self.failurefile = os.path.join(reports_dir, '_no_results.json')

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

        # Build Alert Center API service
        self.alerts_service = build('alertcenter', 'v1beta1', credentials=self.credentials)

    async def dump_alerts(self) -> None:
        """
        Dump all alerts from Google Workspace Alert Center
        """
        self.logger.info('Dumping Alert Center alerts...')
        outfile = os.path.join(self.output_dir, 'alerts.json')

        filter_str = ''
        if self.date_range:
            filter_str = f'createTime >= "{self.date_start}T00:00:00Z" AND createTime <= "{self.date_end}T23:59:59Z"'

        try:
            page_token = None
            total = 0
            while True:
                kwargs = {'pageSize': 100}
                if filter_str:
                    kwargs['filter'] = filter_str
                if page_token:
                    kwargs['pageToken'] = page_token

                response = self.alerts_service.alerts().list(**kwargs).execute()
                alerts = response.get('alerts', [])

                if alerts:
                    with open(outfile, 'a+', encoding='utf-8') as f:
                        for alert in alerts:
                            f.write(json.dumps(alert) + '\n')
                    total += len(alerts)

                page_token = response.get('nextPageToken')
                if not page_token:
                    break

            self.logger.info(f'Finished dumping {total} alerts.')
        except Exception as e:
            self.logger.error(f'Error dumping alerts: {str(e)}')

    async def dump_alert_feedback(self) -> None:
        """
        Dump feedback for all alerts
        """
        self.logger.info('Dumping alert feedback...')
        alerts_file = os.path.join(self.output_dir, 'alerts.json')
        if not os.path.isfile(alerts_file):
            await self.dump_alerts()

        if not os.path.isfile(alerts_file):
            self.logger.warning('No alerts file found. Skipping feedback.')
            return

        outfile = os.path.join(self.output_dir, 'alert_feedback.json')
        alerts = [json.loads(line) for line in open(alerts_file, 'r') if line.strip()]

        for alert in alerts:
            alert_id = alert.get('alertId', '')
            if not alert_id:
                continue
            try:
                response = self.alerts_service.alerts().feedback().list(
                    alertId=alert_id
                ).execute()
                feedbacks = response.get('feedback', [])
                if feedbacks:
                    with open(outfile, 'a+', encoding='utf-8') as f:
                        for fb in feedbacks:
                            fb['alertId'] = alert_id
                            f.write(json.dumps(fb) + '\n')
            except Exception as e:
                self.logger.debug(f'Error getting feedback for alert {alert_id}: {str(e)}')
            await asyncio.sleep(0)

        self.logger.info('Finished dumping alert feedback.')

    async def dump_alert_metadata(self) -> None:
        """
        Dump metadata/details for individual alerts
        """
        self.logger.info('Dumping alert metadata...')
        alerts_file = os.path.join(self.output_dir, 'alerts.json')
        if not os.path.isfile(alerts_file):
            await self.dump_alerts()

        if not os.path.isfile(alerts_file):
            self.logger.warning('No alerts file found. Skipping metadata.')
            return

        outfile = os.path.join(self.output_dir, 'alert_metadata.json')
        alerts = [json.loads(line) for line in open(alerts_file, 'r') if line.strip()]

        for alert in alerts:
            alert_id = alert.get('alertId', '')
            if not alert_id:
                continue
            try:
                response = self.alerts_service.alerts().getMetadata(
                    alertId=alert_id
                ).execute()
                response['alertId'] = alert_id
                with open(outfile, 'a+', encoding='utf-8') as f:
                    f.write(json.dumps(response) + '\n')
            except Exception as e:
                self.logger.debug(f'Error getting metadata for alert {alert_id}: {str(e)}')
            await asyncio.sleep(0)

        self.logger.info('Finished dumping alert metadata.')
