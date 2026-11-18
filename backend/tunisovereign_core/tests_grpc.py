from django.test import TestCase

from grpc_service import tunisovereign_pb2 as pb
from grpc_service.servicer import TelemetryIngestServicer, sign_packet
from tunisovereign_core.models import (
    CooperativeUnit, ResourceNodePlot, StakeholderUser, TelemetryReading,
)

TS = "2026-11-25T10:00:00+00:00"


def packet(node="TEST-NODE-1", metric="MOISTURE", value=50.0, sig=None, gov="Kasserine"):
    return pb.TelemetryPacket(
        node_code=node, governorate=gov, metric_type=metric, value=value,
        iso_timestamp=TS, signature_hmac=sig or sign_packet(node, gov, metric, value, TS),
    )


class StreamTelemetryTests(TestCase):
    def setUp(self):
        owner = StakeholderUser.objects.create_user(username="t_owner", password="x12345678")
        coop = CooperativeUnit.objects.create(name="Coop Test", governorate="Kasserine", daily_quota_limit=1000)
        ResourceNodePlot.objects.create(coop=coop, owner=owner, node_code="TEST-NODE-1", crop_or_sector_type="Olive")
        self.servicer = TelemetryIngestServicer()

    def call(self, *packets):
        return self.servicer.StreamTelemetry(iter(packets), None)

    def test_valid_packet_is_saved_as_grpc(self):
        ack = self.call(packet())
        self.assertEqual((ack.accepted_count, ack.rejected_count), (1, 0))
        self.assertEqual(TelemetryReading.objects.filter(ingestion_protocol="gRPC").count(), 1)

    def test_bad_signature_is_rejected(self):
        ack = self.call(packet(sig="bad"))
        self.assertEqual((ack.accepted_count, ack.rejected_count), (0, 1))
        self.assertEqual(TelemetryReading.objects.count(), 0)

    def test_unknown_node_is_rejected(self):
        ack = self.call(packet(node="UNKNOWN"))
        self.assertEqual(ack.rejected_count, 1)

    def test_invalid_metric_is_rejected(self):
        ack = self.call(packet(metric="BANANA"))
        self.assertEqual(ack.rejected_count, 1)

    def test_low_moisture_triggers_anomaly(self):
        ack = self.call(packet(value=20.0))
        self.assertTrue(ack.anomaly_triggered)
        self.assertTrue(ack.agent_thread_id.startswith("grpc-auto-"))

    def test_normal_moisture_no_anomaly(self):
        self.assertFalse(self.call(packet(value=50.0)).anomaly_triggered)