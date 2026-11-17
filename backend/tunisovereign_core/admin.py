from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import (
    AgentLoopExecution,
    AnomalyAndForecastEvent,
    CooperativeUnit,
    OnChainZKReceipt,
    ResourceNodePlot,
    StakeholderUser,
    TelemetryReading,
)


@admin.register(StakeholderUser)
class StakeholderUserAdmin(UserAdmin):
    list_display = ("username", "role", "governorate", "is_staff")
    list_filter = ("role", "governorate", "is_staff")
    fieldsets = UserAdmin.fieldsets + (
        ("TuniSovereign", {"fields": ("role", "governorate", "wallet_address", "preferred_dialect")}),
    )
    add_fieldsets = UserAdmin.add_fieldsets + (
        ("TuniSovereign", {"fields": ("role", "governorate", "wallet_address", "preferred_dialect")}),
    )


@admin.register(CooperativeUnit)
class CooperativeUnitAdmin(admin.ModelAdmin):
    list_display = ("name", "governorate", "track_domain", "daily_quota_limit")
    list_filter = ("governorate", "track_domain")
    search_fields = ("name",)


@admin.register(ResourceNodePlot)
class ResourceNodePlotAdmin(admin.ModelAdmin):
    list_display = ("node_code", "coop", "owner", "crop_or_sector_type", "allocated_share_pct")
    list_filter = ("coop", "is_valve_or_dispatch_active")
    search_fields = ("node_code",)


@admin.register(TelemetryReading)
class TelemetryReadingAdmin(admin.ModelAdmin):
    list_display = ("node", "metric_type", "value", "timestamp", "ingestion_protocol")
    list_filter = ("metric_type", "ingestion_protocol")
    date_hierarchy = "timestamp"


@admin.register(AnomalyAndForecastEvent)
class AnomalyAndForecastEventAdmin(admin.ModelAdmin):
    list_display = ("node", "anomaly_type", "severity", "isolation_forest_score", "detected_at")
    list_filter = ("severity",)


@admin.register(AgentLoopExecution)
class AgentLoopExecutionAdmin(admin.ModelAdmin):
    list_display = ("thread_id", "trigger_source", "confidence_score", "created_at")
    list_filter = ("trigger_source",)
    search_fields = ("thread_id",)


@admin.register(OnChainZKReceipt)
class OnChainZKReceiptAdmin(admin.ModelAdmin):
    list_display = ("tx_hash", "network_name", "block_number", "is_verified_on_chain")
    list_filter = ("network_name", "is_verified_on_chain")
