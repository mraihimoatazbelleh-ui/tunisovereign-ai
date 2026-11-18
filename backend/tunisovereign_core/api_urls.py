from django.urls import path, include
from rest_framework.routers import DefaultRouter

from .api_rest import (
    CooperativeUnitViewSet, TelemetryReadingViewSet,
    AnomalyAndForecastEventViewSet, OnChainZKReceiptViewSet,
    darja_intent_webhook,
)

router = DefaultRouter()
router.register("cooperatives", CooperativeUnitViewSet, basename="cooperatives")
router.register("telemetry", TelemetryReadingViewSet, basename="telemetry")
router.register("anomalies", AnomalyAndForecastEventViewSet, basename="anomalies")
router.register("zk-receipts", OnChainZKReceiptViewSet, basename="zk-receipts")

urlpatterns = [
    path("api/v1/darja-intent/", darja_intent_webhook),
    path("api/v1/", include(router.urls)),
]
