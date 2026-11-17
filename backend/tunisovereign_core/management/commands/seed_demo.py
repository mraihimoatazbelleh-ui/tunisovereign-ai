import math
import random
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from tunisovereign_core.models import (
    CooperativeUnit,
    ResourceNodePlot,
    StakeholderUser,
    TelemetryReading,
)

DEMO_PASSWORD = "demo1234"
SEED = 42  # fixed seed -> the generated moisture values are reproducible

Role = StakeholderUser.Role

USERS = [
    # username, role, governorate
    ("farmer_kasserine", Role.COOP_MEMBER, "Kasserine"),
    ("farmer_sidibouzid", Role.COOP_MEMBER, "Sidi Bouzid"),
    ("farmer_gafsa", Role.COOP_MEMBER, "Gafsa"),
    ("auditor_gafsa", Role.REGIONAL_AUDITOR, "Gafsa"),
    ("admin_national", Role.NATIONAL_ADMIN, "Tunis"),
    ("agent_mcp", Role.AGENT_SERVICE, "Tunis"),
]

COOPS = [
    # name, governorate, daily quota
    ("Cooperative Sbeitla", "Kasserine", 4200.0),
    ("Cooperative Regueb", "Sidi Bouzid", 3600.0),
    ("Cooperative Metlaoui", "Gafsa", 3000.0),
]

PLOTS = [
    # node_code, coop name, owner username, crop, share %
    ("KAS-SBEITLA-PLOT-04", "Cooperative Sbeitla", "farmer_kasserine", "Olive", 12.0),
    ("SBZ-REGUEB-PLOT-01", "Cooperative Regueb", "farmer_sidibouzid", "Cereals", 10.0),
    ("GAF-METLAOUI-PLOT-02", "Cooperative Metlaoui", "farmer_gafsa", "Dates", 15.0),
]


class Command(BaseCommand):
    help = "Create demo users, cooperatives, plots and 24h of soil-moisture readings."

    @transaction.atomic
    def handle(self, *args, **options):
        User = get_user_model()
        rng = random.Random(SEED)

        users = {}
        for username, role, governorate in USERS:
            user, _ = User.objects.get_or_create(username=username)
            user.role = role
            user.governorate = governorate
            user.is_staff = role == Role.NATIONAL_ADMIN
            user.set_password(DEMO_PASSWORD)
            user.save()
            users[username] = user

        coops = {}
        for name, governorate, quota in COOPS:
            coop, _ = CooperativeUnit.objects.update_or_create(
                name=name,
                defaults={"governorate": governorate, "daily_quota_limit": quota},
            )
            coops[name] = coop

        plots = []
        for code, coop_name, owner, crop, share in PLOTS:
            plot, _ = ResourceNodePlot.objects.update_or_create(
                node_code=code,
                defaults={
                    "coop": coops[coop_name],
                    "owner": users[owner],
                    "crop_or_sector_type": crop,
                    "allocated_share_pct": share,
                },
            )
            plots.append(plot)

        # 24 hourly soil-moisture readings per plot, diurnal pattern + small noise.
        now = timezone.now().replace(minute=0, second=0, microsecond=0)
        TelemetryReading.objects.filter(node__in=plots).delete()
        readings = []
        for plot in plots:
            base = rng.uniform(30, 38)
            for hours_ago in range(23, -1, -1):
                ts = now - timedelta(hours=hours_ago)
                diurnal = -5 * math.sin(2 * math.pi * (ts.hour - 6) / 24)
                value = base + diurnal + rng.gauss(0, 0.6)
                readings.append(
                    TelemetryReading(
                        node=plot,
                        timestamp=ts,
                        metric_type=TelemetryReading.MetricType.SOIL_MOISTURE,
                        value=round(max(5.0, min(60.0, value)), 2),
                        ingestion_protocol=TelemetryReading.Protocol.SIMULATOR,
                    )
                )
        TelemetryReading.objects.bulk_create(readings)

        self.stdout.write(
            self.style.SUCCESS(
                f"Seeded {len(USERS)} users, {len(COOPS)} cooperatives, "
                f"{len(PLOTS)} plots, {len(readings)} readings. "
                f"Password for all demo users: {DEMO_PASSWORD}"
            )
        )
