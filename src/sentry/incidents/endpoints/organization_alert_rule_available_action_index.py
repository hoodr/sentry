from __future__ import absolute_import

from collections import defaultdict

from rest_framework import status
from rest_framework.response import Response

from sentry import features
from sentry.api.exceptions import ResourceDoesNotExist
from sentry.constants import SentryAppStatus
from sentry.incidents.endpoints.bases import OrganizationEndpoint
from sentry.incidents.endpoints.serializers import action_target_type_to_string
from sentry.incidents.logic import get_available_action_integrations_for_org, get_alertable_sentry_apps
from sentry.incidents.models import AlertRuleTriggerAction
from sentry.models import PagerDutyService


class OrganizationAlertRuleAvailableActionIndexEndpoint(OrganizationEndpoint):
    def fetch_pagerduty_services(self, organization, integration_id):
        services = PagerDutyService.objects.filter(
            organization_integration__organization=organization,
            organization_integration__integration_id=integration_id,
        ).values("id", "service_name")
        formatted_services = [
            {"value": service["id"], "label": service["service_name"]} for service in services
        ]
        return formatted_services

    def build_action_response(self, organization, registered_type, integration=None):
        allowed_target_types = [
            action_target_type_to_string[target_type]
            for target_type in registered_type.supported_target_types
        ]

        action_response = {
            "type": registered_type.slug,
            "allowedTargetTypes": allowed_target_types,
        }

        if registered_type.type.value in [
            AlertRuleTriggerAction.Type.PAGERDUTY.value,
            AlertRuleTriggerAction.Type.EMAIL.value,
        ]:
            action_response["inputType"] = "select"
        elif registered_type.type.value in [
            AlertRuleTriggerAction.Type.SLACK.value,
            AlertRuleTriggerAction.Type.MSTEAMS.value,
        ]:
            action_response["inputType"] = "text"

        if integration:
            action_response["integrationName"] = integration.name
            action_response["integrationId"] = integration.id

            if registered_type.type.value == AlertRuleTriggerAction.Type.PAGERDUTY.value:
                action_response["options"] = self.fetch_pagerduty_services(organization, integration.id)
            elif registered_type.type.value == AlertRuleTriggerAction.Type.SENTRY_APP.value:
                action_response["status"] = SentryAppStatus.as_str(integration.status)

        return action_response

    def get(self, request, organization):
        """
        Fetches actions that an alert rule can perform for an organization
        """
        if not features.has("organizations:incidents", organization, actor=request.user):
            raise ResourceDoesNotExist

        actions = []

        integrations = get_available_action_integrations_for_org(organization).order_by("id")
        provider_integrations = defaultdict(list)
        for integration in integrations:
            provider_integrations[integration.provider].append(integration)
        registered_types = AlertRuleTriggerAction.get_registered_types()
        registered_types.sort(key=lambda x: x.slug)

        for registered_type in AlertRuleTriggerAction.get_registered_types():
            if registered_type.integration_provider:
                for integration in provider_integrations[registered_type.integration_provider]:
                    actions.append(
                        self.build_action_response(organization, registered_type, integration)
                    )
            else:
                actions.append(self.build_action_response(organization, registered_type))
        return Response(actions, status=status.HTTP_200_OK)
