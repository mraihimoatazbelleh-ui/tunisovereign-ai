from django.db import connection
from django.test import TransactionTestCase
from django.test.utils import CaptureQueriesContext

from .api_rest import SovereignTokenObtainPairSerializer
from .models import (
    CooperativeUnit, ResourceNodePlot, StakeholderUser,
    AnomalyAndForecastEvent, AgentLoopExecution, OnChainZKReceipt,
)

Role = StakeholderUser.Role


def bearer(user):
    """Authorization header carrying the same custom claims as /api/auth/login/."""
    token = SovereignTokenObtainPairSerializer.get_token(user).access_token
    return {"HTTP_AUTHORIZATION": f"Bearer {token}"}


class GraphQLBase(TransactionTestCase):
    def setUp(self):
        self.auditor = StakeholderUser.objects.create_user(
            username="gql_auditor", password="x", role=Role.REGIONAL_AUDITOR)
        self.member = StakeholderUser.objects.create_user(
            username="gql_member", password="x", role=Role.COOP_MEMBER)

    def _seed(self, prefix, n_coops):
        owner, _ = StakeholderUser.objects.get_or_create(username="owner_test")
        for i in range(n_coops):
            coop = CooperativeUnit.objects.create(
                name=f"{prefix}{i}", governorate="Kasserine", daily_quota_limit=4000)
            for j in range(3):
                node = ResourceNodePlot.objects.create(
                    coop=coop, owner=owner, node_code=f"{prefix}{i}-{j}",
                    crop_or_sector_type="olive")
                AnomalyAndForecastEvent.objects.create(
                    node=node, anomaly_type="LEAK", severity="CRITICAL",
                    isolation_forest_score=-0.4)
                ex = AgentLoopExecution.objects.create(
                    thread_id=f"t-{prefix}{i}-{j}", node=node,
                    trigger_source=AgentLoopExecution.Trigger.MANUAL)
                OnChainZKReceipt.objects.create(
                    agent_execution=ex,
                    zk_commitment_hash=f"0xc{prefix}{i}{j}",
                    tx_hash=f"0xt{prefix}{i}{j}",
                    block_number=1)

    def post(self, query, user=None):
        extra = bearer(user) if user else {}
        return self.client.post("/graphql/", {"query": query},
                                content_type="application/json", **extra)


class GraphQLQueryCountTest(GraphQLBase):
    QUERY = """
    { cooperatives { name nodes { nodeCode
        anomalies { severity }
        executions { threadId finalRecommendation }
        receipts { txHash } } } }
    """

    def _run(self):
        with CaptureQueriesContext(connection) as ctx:
            r = self.post(self.QUERY, self.auditor)
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertNotIn("errors", body)
        return len(ctx), body

    def test_queries_do_not_grow(self):
        self._seed("A", 2)
        small, _ = self._run()
        self._seed("B", 20)
        large, body = self._run()
        self.assertEqual(small, large)
        node = body["data"]["cooperatives"][0]["nodes"][0]
        self.assertTrue(node["receipts"])
        self.assertTrue(node["anomalies"])
        self.assertTrue(node["executions"])


class GraphQLSecurityTest(GraphQLBase):
    def test_request_without_token_is_rejected(self):
        self._seed("S", 1)
        r = self.post("{ cooperatives { name } }")
        self.assertEqual(r.status_code, 401)

    def test_request_with_invalid_token_is_rejected(self):
        r = self.client.post("/graphql/", {"query": "{ cooperatives { name } }"},
                             content_type="application/json",
                             HTTP_AUTHORIZATION="Bearer not-a-real-token")
        self.assertEqual(r.status_code, 401)

    def test_coop_member_can_read_cooperatives_and_receipts(self):
        self._seed("M", 1)
        r = self.post("{ cooperatives { name nodes { nodeCode receipts { txHash } } } }",
                      self.member)
        body = r.json()
        self.assertEqual(r.status_code, 200)
        self.assertNotIn("errors", body)
        self.assertTrue(body["data"]["cooperatives"][0]["nodes"][0]["receipts"])

    def test_coop_member_cannot_read_anomalies(self):
        self._seed("N", 1)
        r = self.post("{ cooperatives { nodes { nodeCode anomalies { severity } } } }",
                      self.member)
        body = r.json()
        self.assertIn("errors", body)
        node = body["data"]["cooperatives"][0]["nodes"][0]
        self.assertIsNone(node["anomalies"])

    def test_coop_member_cannot_read_agent_executions(self):
        self._seed("E", 1)
        r = self.post("{ cooperatives { nodes { executions { threadId } } } }",
                      self.member)
        body = r.json()
        self.assertIn("errors", body)
        self.assertIsNone(body["data"]["cooperatives"][0]["nodes"][0]["executions"])
