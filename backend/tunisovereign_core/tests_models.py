from django.db import IntegrityError, transaction
from django.test import TestCase
from django.utils import timezone

from tunisovereign_core.models import (
    AgentLoopExecution,
    CooperativeUnit,
    OnChainZKReceipt,
    ResourceNodePlot,
    StakeholderUser,
    TelemetryReading,
)


class ModelTestBase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.owner = StakeholderUser.objects.create_user(username="model_owner", password="x")
        cls.coop = CooperativeUnit.objects.create(
            name="Test Coop", governorate="Kasserine", daily_quota_limit=1000.0
        )
        cls.node = ResourceNodePlot.objects.create(
            coop=cls.coop,
            owner=cls.owner,
            node_code="TEST-NODE-01",
            crop_or_sector_type="Olive",
            allocated_share_pct=10.0,
        )

    def make_node(self, code, share):
        return ResourceNodePlot.objects.create(
            coop=self.coop,
            owner=self.owner,
            node_code=code,
            crop_or_sector_type="Cereals",
            allocated_share_pct=share,
        )


class CheckConstraintTests(ModelTestBase):
    def test_zero_quota_is_rejected(self):
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                CooperativeUnit.objects.create(name="Zero", governorate="Gafsa", daily_quota_limit=0)

    def test_negative_quota_is_rejected(self):
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                CooperativeUnit.objects.create(name="Neg", governorate="Gafsa", daily_quota_limit=-5)

    def test_share_above_100_is_rejected(self):
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                self.make_node("TEST-NODE-HIGH", 100.5)

    def test_negative_share_is_rejected(self):
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                self.make_node("TEST-NODE-NEG", -1)

    def test_share_boundaries_0_and_100_are_accepted(self):
        self.make_node("TEST-NODE-ZERO", 0)
        self.make_node("TEST-NODE-FULL", 100)
        self.assertEqual(ResourceNodePlot.objects.filter(coop=self.coop).count(), 3)


class UniquenessAndDefaultsTests(ModelTestBase):
    def test_node_code_is_unique(self):
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                self.make_node("TEST-NODE-01", 10)

    def test_user_default_role_is_coop_member(self):
        self.assertEqual(self.owner.role, StakeholderUser.Role.COOP_MEMBER)

    def test_four_roles_exist(self):
        self.assertEqual(
            {r.value for r in StakeholderUser.Role},
            {"COOP_MEMBER", "REGIONAL_AUDITOR", "NATIONAL_ADMIN", "AGENT_SERVICE"},
        )

    def test_reading_default_protocol_is_grpc(self):
        reading = TelemetryReading.objects.create(
            node=self.node,
            timestamp=timezone.now(),
            metric_type=TelemetryReading.MetricType.SOIL_MOISTURE,
            value=33.3,
        )
        self.assertEqual(reading.ingestion_protocol, "gRPC")

    def test_telemetry_index_covers_node_metric_and_descending_time(self):
        field_sets = [tuple(i.fields) for i in TelemetryReading._meta.indexes]
        self.assertIn(("node", "metric_type", "-timestamp"), field_sets)

    def test_deleting_a_coop_cascades_to_nodes_and_readings(self):
        TelemetryReading.objects.create(
            node=self.node,
            timestamp=timezone.now(),
            metric_type=TelemetryReading.MetricType.SOIL_MOISTURE,
            value=30.0,
        )
        self.coop.delete()
        self.assertEqual(ResourceNodePlot.objects.count(), 0)
        self.assertEqual(TelemetryReading.objects.count(), 0)


class AgentExecutionAndReceiptTests(ModelTestBase):
    def make_execution(self, thread_id):
        return AgentLoopExecution.objects.create(
            thread_id=thread_id, trigger_source=AgentLoopExecution.Trigger.MANUAL
        )

    def test_execution_can_be_created_before_the_loop_finishes(self):
        execution = self.make_execution("thread-early")
        self.assertEqual(execution.final_recommendation, "")
        self.assertEqual(execution.confidence_score, 0.0)

    def test_one_execution_has_at_most_one_receipt(self):
        execution = self.make_execution("thread-one-receipt")
        OnChainZKReceipt.objects.create(
            agent_execution=execution,
            zk_commitment_hash="0x" + "a" * 64,
            tx_hash="0x" + "b" * 64,
            block_number=1,
        )
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                OnChainZKReceipt.objects.create(
                    agent_execution=execution,
                    zk_commitment_hash="0x" + "c" * 64,
                    tx_hash="0x" + "d" * 64,
                    block_number=2,
                )

    def test_receipt_is_reachable_from_the_execution(self):
        execution = self.make_execution("thread-reverse")
        receipt = OnChainZKReceipt.objects.create(
            agent_execution=execution,
            zk_commitment_hash="0x" + "e" * 64,
            tx_hash="0x" + "f" * 64,
            block_number=3,
        )
        self.assertEqual(execution.zk_receipt, receipt)

    def test_receipt_hashes_are_unique(self):
        first = self.make_execution("thread-hash-1")
        second = self.make_execution("thread-hash-2")
        OnChainZKReceipt.objects.create(
            agent_execution=first,
            zk_commitment_hash="0x" + "1" * 64,
            tx_hash="0x" + "2" * 64,
            block_number=4,
        )
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                OnChainZKReceipt.objects.create(
                    agent_execution=second,
                    zk_commitment_hash="0x" + "1" * 64,
                    tx_hash="0x" + "3" * 64,
                    block_number=5,
                )
