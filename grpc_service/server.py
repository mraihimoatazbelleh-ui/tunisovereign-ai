"""Serveur gRPC TuniSovereign (proto3). Lancement : python grpc_service/server.py"""
import os
import sys
import time
from concurrent import futures
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "backend"))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

import django
django.setup()

import grpc
from django.db import close_old_connections
from grpc_service import tunisovereign_pb2_grpc as pb_grpc
from grpc_service.servicer import TelemetryIngestServicer


class ManagedServicer(TelemetryIngestServicer):
    """Ferme les connexions DB du thread après chaque RPC (comme le fait Django après une requête HTTP)."""

    def StreamTelemetry(self, request_iterator, context):
        try:
            return super().StreamTelemetry(request_iterator, context)
        finally:
            close_old_connections()

    def TriggerUrgentAudit(self, request, context):
        try:
            return super().TriggerUrgentAudit(request, context)
        finally:
            close_old_connections()


def serve(port=None):
    port = port or os.getenv("GRPC_PORT", "50051")
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=8))
    pb_grpc.add_TelemetryIngestServiceServicer_to_server(ManagedServicer(), server)
    server.add_insecure_port(f"[::]:{port}")
    server.start()
    print(f"[TuniSovereign gRPC] écoute sur le port {port}")
    try:
        while True:
            time.sleep(3600)
    except KeyboardInterrupt:
        server.stop(0)


if __name__ == "__main__":
    serve()