import uuid

from django.contrib.auth.models import AbstractUser
from django.db import models


class StakeholderUser(AbstractUser):
    class Role(models.TextChoices):
        COOP_MEMBER = "COOP_MEMBER", "Farmer / Citizen / Field Operator"
        REGIONAL_AUDITOR = "REGIONAL_AUDITOR", "Regional GDA / PCT / Municipal Auditor"
        NATIONAL_ADMIN = "NATIONAL_ADMIN", "Governorate / National Ministry Admin"
        AGENT_SERVICE = "AGENT_SERVICE", "Autonomous AI Agent & MCP Service Account"

    role = models.CharField(max_length=24, choices=Role.choices, default=Role.COOP_MEMBER)
    governorate = models.CharField(max_length=64, db_index=True, default="Kasserine")
    wallet_address = models.CharField(max_length=42, blank=True, null=True)
    preferred_dialect = models.CharField(max_length=16, default="ar-TN")

    def __str__(self):
        return f"{self.username} ({self.role})"


class CooperativeUnit(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=120)
    governorate = models.CharField(max_length=64, db_index=True)
    track_domain = models.CharField(max_length=64, default="Track_01_Water_Agri")
    daily_quota_limit = models.FloatField(help_text="Max daily resource/water/medicine quota")
    contract_address = models.CharField(max_length=42, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=models.Q(daily_quota_limit__gt=0),
                name="coop_daily_quota_positive",
            ),
        ]

    def __str__(self):
        return f"{self.name} ({self.governorate})"


class ResourceNodePlot(models.Model):
    coop = models.ForeignKey(CooperativeUnit, on_delete=models.CASCADE, related_name="nodes")
    owner = models.ForeignKey(StakeholderUser, on_delete=models.CASCADE, related_name="owned_nodes")
    node_code = models.CharField(max_length=32, unique=True)
    crop_or_sector_type = models.CharField(max_length=64)
    allocated_share_pct = models.FloatField(default=10.0)
    is_valve_or_dispatch_active = models.BooleanField(default=False)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=models.Q(allocated_share_pct__gte=0) & models.Q(allocated_share_pct__lte=100),
                name="node_share_pct_between_0_and_100",
            ),
        ]

    def __str__(self):
        return self.node_code


class TelemetryReading(models.Model):
    class MetricType(models.TextChoices):
        SOIL_MOISTURE = "MOISTURE", "Soil Moisture (%)"
        AQUIFER_FLOW = "FLOW", "Flow / Dispensation Rate (L/min or Units/h)"
        TEMPERATURE = "TEMP", "Ambient / Cold-Chain Temperature (C)"
        PRESSURE_OR_STOCK = "STOCK", "Piezo Pressure / Inventory Level"

    class Protocol(models.TextChoices):
        GRPC = "gRPC", "gRPC (proto3)"
        REST = "REST", "REST (DRF)"
        SIMULATOR = "SIMULATOR", "Telemetry Simulator"

    node = models.ForeignKey(ResourceNodePlot, on_delete=models.CASCADE, related_name="readings")
    timestamp = models.DateTimeField(db_index=True)
    metric_type = models.CharField(max_length=16, choices=MetricType.choices)
    value = models.FloatField()
    ingestion_protocol = models.CharField(max_length=16, choices=Protocol.choices, default=Protocol.GRPC)

    class Meta:
        # Supports "latest readings per node and metric" queries.
        indexes = [models.Index(fields=["node", "metric_type", "-timestamp"])]

    def __str__(self):
        return f"{self.node_id} {self.metric_type}={self.value} @ {self.timestamp:%Y-%m-%d %H:%M}"


class AnomalyAndForecastEvent(models.Model):
    class Severity(models.TextChoices):
        LOW = "LOW", "Low"
        MEDIUM = "MEDIUM", "Medium"
        CRITICAL = "CRITICAL", "Critical Breach / Leak / Diversion"

    node = models.ForeignKey(ResourceNodePlot, on_delete=models.CASCADE, related_name="anomalies")
    detected_at = models.DateTimeField(auto_now_add=True)
    anomaly_type = models.CharField(max_length=64)
    severity = models.CharField(max_length=16, choices=Severity.choices)
    isolation_forest_score = models.FloatField()
    forecasted_deficit_24h = models.FloatField(default=0.0)

    def __str__(self):
        return f"{self.severity} {self.anomaly_type} on node {self.node_id}"


class AgentLoopExecution(models.Model):
    class Trigger(models.TextChoices):
        DARJA_REQUEST = "DARJA_REQUEST", "Darja request from a farmer"
        ANOMALY_ALERT = "ANOMALY_ALERT", "Anomaly detected by the ML engine"
        SCHEDULED = "SCHEDULED", "Scheduled run"
        MANUAL = "MANUAL", "Manual trigger"

    
    thread_id = models.CharField(max_length=64, db_index=True)
    node = models.ForeignKey(
        ResourceNodePlot, on_delete=models.SET_NULL,
        null=True, blank=True, related_name="agent_executions",
    )
    trigger_source = models.CharField(max_length=64, choices=Trigger.choices)
    darja_transcript = models.TextField(blank=True)
    parsed_intent_json = models.JSONField(default=dict)
    mcp_tools_invoked = models.JSONField(default=list)
    skills_executed = models.JSONField(default=list)
    # The agent creates the row before the loop finishes, so these start empty.
    final_recommendation = models.TextField(blank=True)
    confidence_score = models.FloatField(default=0.0)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.thread_id} ({self.trigger_source})"


class OnChainZKReceipt(models.Model):
    # One execution produces at most one on-chain receipt.
    agent_execution = models.OneToOneField(
        AgentLoopExecution, on_delete=models.CASCADE, related_name="zk_receipt"
    )
    zk_commitment_hash = models.CharField(max_length=66, unique=True)
    public_inputs_json = models.JSONField(default=dict)
    tx_hash = models.CharField(max_length=66, unique=True)
    block_number = models.PositiveIntegerField()
    network_name = models.CharField(max_length=32, default="Foundry-Anvil-Local")
    is_verified_on_chain = models.BooleanField(default=True)

    def __str__(self):
        return f"Receipt {self.tx_hash[:12]}..."
