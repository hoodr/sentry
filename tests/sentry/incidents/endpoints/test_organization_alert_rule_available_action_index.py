from __future__ import absolute_import

from sentry.constants import SentryAppStatus
from sentry.models import Integration
from sentry.testutils import APITestCase


class OrganizationAlertRuleAvailableActionIndexEndpointTest(APITestCase):
    endpoint = "sentry-api-0-organization-alert-rule-available-actions"

    def setUp(self):
        super(OrganizationAlertRuleAvailableActionIndexEndpointTest, self).setUp()
        self.login_as(self.user)

    def create_integration_response(self, type, integration=None):
        response = {"type": type}
        if type == "email":
            response["allowedTargetTypes"] = ["user", "team"]
            response["inputType"] = "select"
        elif type == "pagerduty":
            response["allowedTargetTypes"] = ["specific"]
            response["inputType"] = "select"
        elif type == "slack":
            response["allowedTargetTypes"] = ["specific"]
            response["inputType"] = "text"
        elif type == "sentry_app":
            response["allowedTargetTypes"] = ["sentry_app"]
            response["status"] = SentryAppStatus.as_str(integration.status)
        elif type == "msteams":
            response["allowedTargetTypes"] = ["specific"]
            response["inputType"] = "text"

        if integration:
            response["integrationName"] = integration.name
            response["integrationId"] = integration.id

        return response

    def test_no_integrations(self):
        with self.feature("organizations:incidents"):
            resp = self.get_valid_response(self.organization.slug)

        assert resp.data == [self.create_integration_response("email")]

    def test_simple(self):
        integration = Integration.objects.create(external_id="1", provider="slack")
        integration.add_organization(self.organization)

        with self.feature("organizations:incidents"):
            resp = self.get_valid_response(self.organization.slug)

        assert resp.data == [
            self.create_integration_response("email"),
            self.create_integration_response("slack", integration),
        ]

    def test_duplicate_integrations(self):
        integration = Integration.objects.create(external_id="1", provider="slack", name="slack 1")
        integration.add_organization(self.organization)
        other_integration = Integration.objects.create(
            external_id="2", provider="slack", name="slack 2"
        )
        other_integration.add_organization(self.organization)

        with self.feature("organizations:incidents"):
            resp = self.get_valid_response(self.organization.slug)

        assert resp.data == [
            self.create_integration_response("email"),
            self.create_integration_response("slack", integration),
            self.create_integration_response("slack", other_integration),
        ]

    def test_no_feature(self):
        self.create_team(organization=self.organization, members=[self.user])
        resp = self.get_response(self.organization.slug)
        assert resp.status_code == 404

    def test_sentry_apps(self):
        sentry_app = self.create_sentry_app(
            name="foo", organization=self.organization, is_alertable=True, verify_install=False
        )
        self.create_sentry_app_installation(
            slug=sentry_app.slug, organization=self.organization, user=self.user
        )

        with self.feature(
            ["organizations:incidents", "organizations:integrations-sentry-app-metric-alerts"]
        ):
            resp = self.get_valid_response(self.organization.slug)

        assert resp.data == [
            self.create_integration_response("sentry_app", sentry_app),
            self.create_integration_response("email"),
        ]
