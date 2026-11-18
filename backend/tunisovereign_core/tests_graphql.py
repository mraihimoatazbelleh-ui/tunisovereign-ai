from django.test import TransactionTestCase
from django.test.utils import CaptureQueriesContext
from django.db import connection

from .models import (
    CooperativeUnit, ResourceNodePlot, StakeholderUser,
    AnomalyAndForecastEvent, AgentLoopExecution, OnChainZKReceipt,
)


class GraphQLQueryCountTest(TransactionTestCase):
    QUERY = """
    { cooperatives { name nodes { nodeCode
        anomalies { severity }
        receipts { txHash } } } }
    """

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

    def _run(self):
        with CaptureQueriesContext(connection) as ctx:
            r = self.client.post("/graphql/", {"query": self.QUERY},
                                 content_type="application/json")
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
