"""Simulateur de télémétrie tunisienne : génère des mesures diurnes signées et les envoie par gRPC."""
import argparse
import hashlib
import hmac
import math
import os
import random
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# Mêmes node_code que backend/.../seed_demo.py
NODES = [
    {"node_code": "KAS-SBEITLA-PLOT-04", "governorate": "Kasserine", "base_moisture": 54.0, "base_temp": 27.0},
    {"node_code": "SBZ-REGUEB-PLOT-01", "governorate": "Sidi_Bouzid", "base_moisture": 52.0, "base_temp": 28.5},
    {"node_code": "GAF-METLAOUI-PLOT-02", "governorate": "Gafsa", "base_moisture": 49.0, "base_temp": 30.0},
]


def sign(node_code, governorate, metric_type, value, iso_ts, secret):
    payload = f"{node_code}|{governorate}|{metric_type}|{value:.2f}|{iso_ts}"
    return hmac.new(secret.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256).hexdigest()


def generate(hours=24, anomaly_hour=14, seed=42, secret="tunisovereign-hmac", tamper=False):
    """Liste de dicts : un par (heure, nœud, métrique). Reproductible grâce à `seed`."""
    rng = random.Random(seed)
    start = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0) - timedelta(hours=hours)
    out = []
    for h in range(hours):
        ts = start + timedelta(hours=h)
        iso = ts.isoformat()
        hod = ts.hour
        for n in NODES:
            moisture = n["base_moisture"] + 5.0 * math.sin(2 * math.pi * hod / 24) + rng.uniform(-1.5, 1.5)
            temp = n["base_temp"] - 4.5 * math.cos(2 * math.pi * hod / 24) + rng.uniform(-0.8, 0.8)
            pump_on = 6 <= hod < 10 or 17 <= hod < 20
            flow = (120.0 if pump_on else 8.0) + rng.uniform(-3, 3)

            if anomaly_hour is not None and h in (anomaly_hour, anomaly_hour + 1) and n["governorate"] == "Kasserine":
                moisture -= 24.5   # fuite ou vol d'eau
                temp += 9.5        # vague de chaleur (sirocco)

            for metric, value in (("MOISTURE", moisture), ("TEMP", temp), ("FLOW", max(0.0, flow))):
                value = round(value, 2)
                sig = "tampered" if tamper else sign(n["node_code"], n["governorate"], metric, value, iso, secret)
                out.append({"node_code": n["node_code"], "governorate": n["governorate"],
                            "metric_type": metric, "value": value, "iso_timestamp": iso, "signature_hmac": sig})
    return out


def stream_to_grpc(packets, host):
    import grpc
    from grpc_service import tunisovereign_pb2 as pb, tunisovereign_pb2_grpc as pb_grpc

    def gen():
        for p in packets:
            yield pb.TelemetryPacket(**p)

    with grpc.insecure_channel(host) as channel:
        stub = pb_grpc.TelemetryIngestServiceStub(channel)
        return stub.StreamTelemetry(gen())


def main():
    ap = argparse.ArgumentParser(description="Simulateur de télémétrie TuniSovereign")
    ap.add_argument("--hours", type=int, default=24)
    ap.add_argument("--anomaly-hour", type=int, default=14)
    ap.add_argument("--no-anomaly", action="store_true")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--host", default=os.getenv("GRPC_HOST", "localhost:50051"))
    ap.add_argument("--dry-run", action="store_true", help="génère sans envoyer")
    ap.add_argument("--tamper", action="store_true", help="fausse les signatures (test de rejet)")
    a = ap.parse_args()

    secret = os.getenv("GRPC_HMAC_SECRET", "tunisovereign-hmac")
    packets = generate(a.hours, None if a.no_anomaly else a.anomaly_hour, a.seed, secret, a.tamper)
    low = [p for p in packets if p["metric_type"] == "MOISTURE" and p["value"] < 35.0]
    print(f"{len(packets)} paquets générés, {len(low)} sous le seuil critique (35 %).")

    if a.dry_run:
        return
    ack = stream_to_grpc(packets, a.host)
    print(f"accepted={ack.accepted_count} rejected={ack.rejected_count} "
          f"anomaly={ack.anomaly_triggered} thread={ack.agent_thread_id}")


if __name__ == "__main__":
    main()