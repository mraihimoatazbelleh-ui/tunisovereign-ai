from collections import defaultdict

import strawberry
import strawberry_django

from .models import CooperativeUnit, ResourceNodePlot, AnomalyAndForecastEvent


async def load_nodes(coop_ids):
    grouped = defaultdict(list)
    async for n in ResourceNodePlot.objects.filter(coop_id__in=coop_ids):
        grouped[n.coop_id].append(n)
    return [grouped.get(c, []) for c in coop_ids]


async def load_anomalies(node_ids):
    grouped = defaultdict(list)
    qs = (AnomalyAndForecastEvent.objects
          .filter(node_id__in=node_ids).order_by("-detected_at"))
    async for a in qs:
        if len(grouped[a.node_id]) < 10:
            grouped[a.node_id].append(a)
    return [grouped.get(n, []) for n in node_ids]


@strawberry_django.type(AnomalyAndForecastEvent)
class AnomalyType:
    id: strawberry.ID
    anomaly_type: str
    severity: str
    isolation_forest_score: float
    forecasted_deficit_24h: float


@strawberry_django.type(ResourceNodePlot)
class NodeType:
    id: strawberry.ID
    node_code: str
    crop_or_sector_type: str
    is_valve_or_dispatch_active: bool

    @strawberry.field
    async def anomalies(self, info: strawberry.Info) -> list[AnomalyType]:
        return await info.context["anomalies_loader"].load(self.id)


@strawberry_django.type(CooperativeUnit)
class CooperativeType:
    id: strawberry.ID
    name: str
    governorate: str
    daily_quota_limit: float

    @strawberry.field
    async def nodes(self, info: strawberry.Info) -> list[NodeType]:
        return await info.context["nodes_loader"].load(self.id)


@strawberry.type
class Query:
    cooperatives: list[CooperativeType] = strawberry_django.field()


schema = strawberry.Schema(query=Query)
