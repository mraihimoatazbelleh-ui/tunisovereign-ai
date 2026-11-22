"""Logique d'ingestion gRPC : vérification HMAC, validation, écriture en base."""
import hashlib
import hmac
import os
import uuid

from django.utils import timezone
from django.utils.dateparse import parse_datetime
from datetime import timezone as dt_timezone

from tunisovereign_core.models import ResourceNodePlot, TelemetryReading
from grpc_service import tunisovereign_pb2 as pb
from grpc_service import tunisovereign_pb2_grpc as pb_grpc

CRITICAL_MOISTURE = 35.0
BATCH_SIZE = 200


def _secret() -> bytes:
    return os.getenv("GRPC_HMAC_SECRET", "tunisovereign-hmac").encode("utf-8")


def sign_packet(node_code, governorate, metric_type, value, iso_ts) -> str:
    payload = f"{node_code}|{governorate}|{metric_type}|{value:.2f}|{iso_ts}"
    return hmac.new(_secret(), payload.encode("utf-8"), hashlib.sha256).hexdigest()


class TelemetryIngestServicer(pb_grpc.TelemetryIngestServiceServicer):

    def StreamTelemetry(self, request_iterator, context):
        accepted = rejected = 0
        anomaly, thread_id = False, ""
        nodes, batch = {}, []
        valid_metrics = set(TelemetryReading.MetricType.values)
        try:
            for p in request_iterator:
                expected = sign_packet(p.node_code, p.governorate, p.metric_type, p.value, p.iso_timestamp)
                ts = parse_datetime(p.iso_timestamp)
                if (not hmac.compare_digest(expected, p.signature_hmac)
                        or ts is None or p.metric_type not in valid_metrics):
                    rejected += 1
                    continue
                if timezone.is_naive(ts):
                    ts = timezone.make_aware(ts,dt_timezone.utc)

                if p.node_code not in nodes:
                    nodes[p.node_code] = ResourceNodePlot.objects.filter(node_code=p.node_code).first()
                node = nodes[p.node_code]
                if node is None:
                    rejected += 1
                    continue

                batch.append(TelemetryReading(
                    node=node, timestamp=ts, metric_type=p.metric_type,
                    value=p.value, ingestion_protocol=TelemetryReading.Protocol.GRPC,
                ))
                accepted += 1

                if p.metric_type == TelemetryReading.MetricType.SOIL_MOISTURE and p.value < CRITICAL_MOISTURE:
                    anomaly = True
                    thread_id = thread_id or f"grpc-auto-{p.node_code}-{uuid.uuid4().hex[:8]}"

                if len(batch) >= BATCH_SIZE:
                    TelemetryReading.objects.bulk_create(batch)
                    batch.clear()
            if batch:
                TelemetryReading.objects.bulk_create(batch)
        finally:
            nodes.clear()

        return pb.IngestAck(accepted_count=accepted, rejected_count=rejected,
                            anomaly_triggered=anomaly, agent_thread_id=thread_id)

    def TriggerUrgentAudit(self, request, context):
        # Branchement réel sur l'agent LangGraph : semaine 3.
        return pb.AuditResponse(status="QUEUED", tx_hash="")