from __future__ import absolute_import

import logging
import six

from sentry.incidents.models import IncidentStatus
from sentry.integrations.metric_alerts import incident_attachment_info
from sentry.models import PagerDutyService
from sentry.shared_integrations.exceptions import ApiError

from .client import PagerDutyClient

logger = logging.getLogger("sentry.integrations.pagerduty")


def build_incident_attachment(incident, integration_key, metric_value=None):
    data = incident_attachment_info(incident, metric_value)
    if incident.status == IncidentStatus.CRITICAL.value:
        severity = "critical"
    elif incident.status == IncidentStatus.WARNING.value:
        severity = "warning"
    elif incident.status == IncidentStatus.CLOSED.value:
        severity = "info"

    event_action = "resolve"
    if incident.status in [IncidentStatus.WARNING.value, IncidentStatus.CRITICAL.value]:
        event_action = "trigger"

    footer_text = "Sentry Incident | {}".format(data["ts"].strftime("%b %d"))

    return {
        "routing_key": integration_key,
        "event_action": event_action,
        "dedup_key": "incident_{}_{}".format(incident.organization_id, incident.identifier),
        "payload": {
            "summary": data["text"],
            "severity": severity,
            "source": incident.identifier,
            "custom_details": footer_text,
        },
        "links": [{"href": data["title_link"], "text": data["title"]}],
    }


def send_incident_alert_notification(action, incident, metric_value):
    integration = action.integration
    service = PagerDutyService.objects.get(id=action.target_identifier)
    integration_key = service.integration_key
    client = PagerDutyClient(integration_key=integration_key)
    attachment = build_incident_attachment(incident, integration_key, metric_value)

    try:
        client.send_trigger(attachment)
    except ApiError as e:
        logger.info(
            "rule.fail.pagerduty_metric_alert",
            extra={
                "error": six.text_type(e),
                "service_name": service.service_name,
                "service_id": service.id,
                "integration_id": integration.id,
            },
        )
        raise e
