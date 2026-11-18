from django.test import TransactionTestCase
from django.test.utils import CaptureQueriesContext
from django.db import connection

from .models import CooperativeUnit, ResourceNodePlot, StakeholderUser


class GraphQLQueryCountTest(TransactionTestCase):
    QUERY = "{ cooperatives { name nodes { nodeCode anomalies { severity } } } }"

    def _seed(self, prefix, n_coops):
        owner, _ = StakeholderUser.objects.get_or_create(username="owner_test")
        for i in range(n_coops):
            coop = CooperativeUnit.objects.create(
                name=f"{prefix}{i}", governorate="Kasserine", daily_quota_limit=4000)
            for j in range(3):
                ResourceNodePlot.objects.create(
                    coop=coop, owner=owner, node_code=f"{prefix}{i}-{j}",
                    crop_or_sector_type="olive")

    def _count(self):
        with CaptureQueriesContext(connection) as ctx:
            r = self.client.post("/graphql/", {"query": self.QUERY},
                                 content_type="application/json")
        self.assertEqual(r.status_code, 200)
        self.assertNotIn("errors", r.json())
        return len(ctx)

    def test_queries_do_not_grow(self):
        self._seed("A", 2)
        small = self._count()
        self._seed("B", 20)
        large = self._count()
        self.assertEqual(small, large)
