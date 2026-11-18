from django.utils import timezone
from rest_framework.test import APITestCase

from .models import (
    StakeholderUser, CooperativeUnit, ResourceNodePlot, TelemetryReading,
)


class RestApiTests(APITestCase):
    def setUp(self):
        self.member = StakeholderUser.objects.create_user(
            username="member", password="x", role="COOP_MEMBER")
        self.auditor = StakeholderUser.objects.create_user(
            username="auditor", password="x", role="REGIONAL_AUDITOR")
        self.coop = CooperativeUnit.objects.create(
            name="Coop Test", governorate="Kasserine", daily_quota_limit=4000)
        self.node = ResourceNodePlot.objects.create(
            coop=self.coop, owner=self.member, node_code="TST-01",
            crop_or_sector_type="olive")
        TelemetryReading.objects.create(
            node=self.node, timestamp=timezone.now(),
            metric_type="MOISTURE", value=40.0)
        TelemetryReading.objects.create(
            node=self.node, timestamp=timezone.now(),
            metric_type="TEMP", value=30.0)

    def test_unauthenticated_is_rejected(self):
        r = self.client.get("/api/v1/cooperatives/")
        self.assertIn(r.status_code, (401, 403))

    def test_member_cannot_read_anomalies(self):
        self.client.force_authenticate(self.member)
        r = self.client.get("/api/v1/anomalies/")
        self.assertEqual(r.status_code, 403)

    def test_auditor_can_read_anomalies(self):
        self.client.force_authenticate(self.auditor)
        r = self.client.get("/api/v1/anomalies/")
        self.assertEqual(r.status_code, 200)

    def test_list_cooperatives(self):
        self.client.force_authenticate(self.member)
        r = self.client.get("/api/v1/cooperatives/")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["count"], 1)

    def test_create_cooperative_201(self):
        self.client.force_authenticate(self.member)
        r = self.client.post("/api/v1/cooperatives/", {
            "name": "Nouvelle", "governorate": "Gafsa",
            "daily_quota_limit": 4200}, format="json")
        self.assertEqual(r.status_code, 201)

    def test_negative_quota_400(self):
        self.client.force_authenticate(self.member)
        r = self.client.post("/api/v1/cooperatives/", {
            "name": "Bad", "governorate": "Gafsa",
            "daily_quota_limit": -5}, format="json")
        self.assertEqual(r.status_code, 400)
        self.assertIn("daily_quota_limit", r.json())

    def test_unknown_cooperative_404(self):
        self.client.force_authenticate(self.member)
        r = self.client.get(
            "/api/v1/cooperatives/00000000-0000-0000-0000-000000000000/")
        self.assertEqual(r.status_code, 404)

    def test_filter_by_governorate(self):
        CooperativeUnit.objects.create(
            name="Autre", governorate="Gafsa", daily_quota_limit=3000)
        self.client.force_authenticate(self.member)
        r = self.client.get("/api/v1/cooperatives/?governorate=Kasserine")
        self.assertEqual(r.json()["count"], 1)

    def test_telemetry_filter_by_metric(self):
        self.client.force_authenticate(self.member)
        r = self.client.get("/api/v1/telemetry/?metric_type=MOISTURE")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["count"], 1)

    def test_moisture_out_of_range_400(self):
        self.client.force_authenticate(self.member)
        r = self.client.post("/api/v1/telemetry/", {
            "node": self.node.id, "timestamp": "2026-11-18T10:00:00Z",
            "metric_type": "MOISTURE", "value": 150}, format="json")
        self.assertEqual(r.status_code, 400)

    def test_darja_empty_400(self):
        r = self.client.post("/api/v1/darja-intent/", {}, format="json")
        self.assertEqual(r.status_code, 400)

    def test_darja_agent_unavailable_503(self):
        r = self.client.post("/api/v1/darja-intent/",
                             {"text": "nheb nsqi"}, format="json")
        self.assertEqual(r.status_code, 503)
