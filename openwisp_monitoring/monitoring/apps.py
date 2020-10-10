from datetime import datetime
from time import sleep

import pytz
from django.apps import AppConfig
from django.conf import settings
from django.utils.translation import gettext_lazy as _
from requests.exceptions import ConnectionError
from swapper import load_model

from ..db import timeseries_db
from .configuration import get_metric_configuration, register_metric_notifications
from .signals import post_metric_write


class MonitoringConfig(AppConfig):
    name = 'openwisp_monitoring.monitoring'
    label = 'monitoring'
    verbose_name = _('Network Monitoring')
    max_retries = 5
    retry_delay = 3

    def ready(self):
        self.create_database()
        setattr(settings, 'OPENWISP_ADMIN_SHOW_USERLINKS_BLOCK', True)
        metrics = get_metric_configuration()
        for metric_name, metric_config in metrics.items():
            register_metric_notifications(metric_name, metric_config)
        post_metric_write.connect(
            check_metric_threshold,
            sender=load_model('monitoring', 'Metric'),
            dispatch_uid='check_threshold',
        )

    def create_database(self):
        # create Timeseries database if it doesn't exist yet
        for attempt_number in range(1, self.max_retries + 1):
            try:
                timeseries_db.create_database()
                return
            except ConnectionError as e:
                self.warn_and_delay(attempt_number)
                if attempt_number == self.max_retries:
                    raise e

    def warn_and_delay(self, attempt_number):
        print(
            'Got error while connecting to timeseries database. '
            f'Retrying again in 3 seconds (attempt n. {attempt_number} out of 5).'
        )
        sleep(self.retry_delay)


def check_metric_threshold(sender, metric, values, send_alert=True, **kwargs):
    time = kwargs.get('time')
    if isinstance(time, str):
        time = datetime.strptime(kwargs.get('time'), '%Y-%m-%dT%H:%M:%S.%fZ')
        time = pytz.utc.localize(time)
    metric.check_threshold(
        values[metric.field_name], time, kwargs.get('rp'), send_alert
    )
