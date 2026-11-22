"""
Django 6 REST API Layer (Django REST Framework + SimpleJWT)
Exposes:
- POST /api/auth/register/ and POST /api/auth/login/ (Custom JWT claims: role, governorate, wallet_address)
- GET/POST /api/v1/cooperatives/, /api/v1/telemetry/, /api/v1/anomalies/, /api/v1/zk-receipts/
- POST /api/v1/darja-intent/ (Ingests Tunisian Darja voice transcript or text and triggers LangGraph loop)
"""
from rest_framework import serializers, viewsets, permissions, status, generics
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.response import Response
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from rest_framework_simplejwt.views import TokenObtainPairView

from .models import (
    StakeholderUser,
    CooperativeUnit,
    ResourceNodePlot,
    TelemetryReading,
    AnomalyAndForecastEvent,
    AgentLoopExecution,
    OnChainZKReceipt,
)



# ============================================================================
# 1. Custom SimpleJWT Claims Serializer (Role, Governorate & Wallet Address)
# ============================================================================
class SovereignTokenObtainPairSerializer(TokenObtainPairSerializer):
    @classmethod
    def get_token(cls, user: StakeholderUser):
        token = super().get_token(user)
        token["role"] = user.role
        token["governorate"] = user.governorate
        token["wallet_address"] = user.wallet_address or ""
        token["preferred_dialect"] = user.preferred_dialect
        return token


class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, min_length=8)

    class Meta:
        model = StakeholderUser
        # Pas de "role" : sinon n'importe qui s'inscrirait en NATIONAL_ADMIN
        fields = ["username", "email", "password", "governorate",
                  "wallet_address", "preferred_dialect"]

    def create(self, validated_data):
        return StakeholderUser.objects.create_user(**validated_data)


class RegisterView(generics.CreateAPIView):
    serializer_class = RegisterSerializer
    permission_classes = [permissions.AllowAny]


class SovereignTokenObtainPairView(TokenObtainPairView):
    serializer_class = SovereignTokenObtainPairSerializer


# ============================================================================
# 2. Role-Based Permission Classes
# ============================================================================
class IsCoopMember(permissions.BasePermission):
    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated)


class IsRegionalAuditor(permissions.BasePermission):
    def has_permission(self, request, view):
        return bool(
            request.user
            and request.user.is_authenticated
            and request.user.role in ("REGIONAL_AUDITOR", "NATIONAL_ADMIN", "AGENT_SERVICE")
        )


class IsNationalAdmin(permissions.BasePermission):
    def has_permission(self, request, view):
        return bool(
            request.user
            and request.user.is_authenticated
            and request.user.role == "NATIONAL_ADMIN"
        )


# ============================================================================
# 3. Model Serializers
# ============================================================================
class CooperativeUnitSerializer(serializers.ModelSerializer):
    class Meta:
        model = CooperativeUnit
        fields = "__all__"
        read_only_fields = ["id", "created_at"]

    def validate_daily_quota_limit(self, value):
        if value <= 0:
            raise serializers.ValidationError("Le quota doit être strictement positif.")
        return value


class ResourceNodePlotSerializer(serializers.ModelSerializer):
    class Meta:
        model = ResourceNodePlot
        fields = "__all__"


class TelemetryReadingSerializer(serializers.ModelSerializer):
    class Meta:
        model = TelemetryReading
        fields = "__all__"

    def validate(self, data):
        if data.get("metric_type") == TelemetryReading.MetricType.SOIL_MOISTURE:
            if not 0 <= data["value"] <= 100:
                raise serializers.ValidationError(
                    {"value": "L'humidité doit être comprise entre 0 et 100."}
                )
        return data

class AnomalyAndForecastEventSerializer(serializers.ModelSerializer):
    class Meta:
        model = AnomalyAndForecastEvent
        fields = "__all__"


class OnChainZKReceiptSerializer(serializers.ModelSerializer):
    class Meta:
        model = OnChainZKReceipt
        fields = "__all__"


class AgentLoopExecutionSerializer(serializers.ModelSerializer):
    zk_receipt = OnChainZKReceiptSerializer(read_only=True)

    class Meta:
        model = AgentLoopExecution
        fields = "__all__"


# ============================================================================
# 4. DRF ViewSets & Darja Intent Webhook
# ============================================================================
class CooperativeUnitViewSet(viewsets.ModelViewSet):
    queryset = CooperativeUnit.objects.all().order_by("-created_at")
    serializer_class = CooperativeUnitSerializer
    filterset_fields = ["governorate"]

    def get_permissions(self):
        # Read: any authenticated member. Write: national admin only.
        if self.action in ("list", "retrieve"):
            return [IsCoopMember()]
        return [IsNationalAdmin()]


class TelemetryReadingViewSet(viewsets.ModelViewSet):
    queryset = TelemetryReading.objects.select_related("node").order_by("-timestamp")
    serializer_class = TelemetryReadingSerializer
    filterset_fields = ["node", "metric_type"]

    def get_permissions(self):
        # Read: any authenticated member. Write: auditor, admin or agent service.
        if self.action in ("list", "retrieve"):
            return [IsCoopMember()]
        return [IsRegionalAuditor()]


class AnomalyAndForecastEventViewSet(viewsets.ModelViewSet):
    queryset = AnomalyAndForecastEvent.objects.select_related("node").order_by("-detected_at")
    serializer_class = AnomalyAndForecastEventSerializer
    filterset_fields = ["node", "severity"]

    def get_permissions(self):
        # Read: auditor, admin or agent service. Write: national admin only.
        if self.action in ("list", "retrieve"):
            return [IsRegionalAuditor()]
        return [IsNationalAdmin()]

class OnChainZKReceiptViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = OnChainZKReceipt.objects.select_related("agent_execution").order_by("-block_number")
    serializer_class = OnChainZKReceiptSerializer
    permission_classes = [IsCoopMember]
    filterset_fields = ["network_name", "is_verified_on_chain"]



@api_view(["POST"])
@permission_classes([IsCoopMember])
def darja_intent_webhook(request):
    """
    POST /api/v1/darja-intent/
    Accepts a Tunisian Darja transcript and sensor telemetry snapshot,
    executes the stateful LangGraph loop + FastMCP tool + ZK settlement skill,
    and returns the structured execution trace and on-chain receipt.
    """
    payload = request.data

    if not (payload.get("darja_input") or payload.get("text")):
        return Response(
            {"error": "darja_input requis"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    try:
        moisture = float(payload.get("moisture_pct", 28.4))
        temp = float(payload.get("temp_c", 37.2))
        flow = float(payload.get("flow_l_min", 182.0))
    except (TypeError, ValueError):
        return Response(
            {"error": "moisture_pct, temp_c et flow_l_min doivent être des nombres"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    try:
        from agent.langgraph_agent import run_sovereign_agent_loop
    except ImportError:
        return Response(
            {"error": "Agent LangGraph pas encore disponible"},
            status=status.HTTP_503_SERVICE_UNAVAILABLE,
        )

    state_out = run_sovereign_agent_loop({
        "thread_id": payload.get("thread_id", "drf-darja-webhook-001"),
        "node_code": payload.get("node_code", "KAS-SBEITLA-PLOT-04"),
        "darja_input": payload.get(
            "darja_input",
            payload.get("text", ""),
        ),
        "moisture_pct": moisture,
        "temp_c": temp,
        "flow_l_min": flow,
        "parsed_intent": {},
        "anomaly_report": {},
        "mcp_allocation": {},
        "zk_receipt": {},
        "skills_trace": [],
        "final_explanation": "",
    })

    return Response(state_out, status=status.HTTP_200_OK)
