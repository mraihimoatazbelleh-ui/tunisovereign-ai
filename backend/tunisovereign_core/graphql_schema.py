from collections import defaultdict

import strawberry
import strawberry_django

from .models import (
    CooperativeUnit,
    ResourceNodePlot,
    AnomalyAndForecastEvent,
    AgentLoopExecution,
    OnChainZKReceipt,
)

# Same rule as the REST API: anomalies and agent traces are not for field members.
PRIVILEGED_ROLES = {"REGIONAL_AUDITOR", "NATIONAL_ADMIN", "AGENT_SERVICE"}


def require_privileged(info: strawberry.Info, what: str):
    if info.context.get("role") not in PRIVILEGED_ROLES:
        raise PermissionError(f"Your role is not allowed to read {what}.")


# ---------- Loaders : une seule requete SQL par niveau ----------

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
        if len(grouped[a.node_id]) < 10:  # 10 dernieres anomalies par node
            grouped[a.node_id].append(a)
    return [grouped.get(n, []) for n in node_ids]


async def load_executions(node_ids):
    grouped = defaultdict(list)
    qs = (AgentLoopExecution.objects
          .filter(node_id__in=node_ids).order_by("-created_at"))
    async for e in qs:
        if len(grouped[e.node_id]) < 10:  # 10 dernieres executions par node
            grouped[e.node_id].append(e)
    return [grouped.get(n, []) for n in node_ids]


async def load_receipts(node_ids):
    grouped = defaultdict(list)
    qs = (OnChainZKReceipt.objects
          .filter(agent_execution__node_id__in=node_ids)
          .select_related("agent_execution")
          .order_by("-block_number"))
    async for r in qs:
        grouped[r.agent_execution.node_id].append(r)
    return [grouped.get(n, []) for n in node_ids]


# ---------- Types ----------

@strawberry_django.type(OnChainZKReceipt)
class ReceiptType:
    id: strawberry.ID
    zk_commitment_hash: str
    tx_hash: str
    block_number: int
    network_name: str
    is_verified_on_chain: bool


@strawberry_django.type(AnomalyAndForecastEvent)
class AnomalyType:
    id: strawberry.ID
    anomaly_type: str
    severity: str
    isolation_forest_score: float
    forecasted_deficit_24h: float


@strawberry_django.type(AgentLoopExecution)
class ExecutionType:
    id: strawberry.ID
    thread_id: str
    trigger_source: str
    darja_transcript: str
    final_recommendation: str
    confidence_score: float


@strawberry_django.type(ResourceNodePlot)
class NodeType:
    id: strawberry.ID
    node_code: str
    crop_or_sector_type: str
    is_valve_or_dispatch_active: bool

    @strawberry.field
    async def anomalies(self, info: strawberry.Info) -> list[AnomalyType] | None:
        require_privileged(info, "anomalies")
        return await info.context["anomalies_loader"].load(self.id)

    @strawberry.field
    async def executions(self, info: strawberry.Info) -> list[ExecutionType] | None:
        require_privileged(info, "agent executions")
        return await info.context["executions_loader"].load(self.id)

    @strawberry.field
    async def receipts(self, info: strawberry.Info) -> list[ReceiptType]:
        return await info.context["receipts_loader"].load(self.id)


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
