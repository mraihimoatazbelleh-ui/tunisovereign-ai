from django.http import JsonResponse
from django.urls import path
from django.views.decorators.csrf import csrf_exempt
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import AccessToken
from strawberry.django.views import AsyncGraphQLView
from strawberry.dataloader import DataLoader

from .graphql_schema import (
    schema, load_nodes, load_anomalies, load_executions, load_receipts,
)


def read_role(request):
    """Role claim of a valid Bearer access token, or None (signature and expiry are checked)."""
    scheme, _, raw = request.headers.get("Authorization", "").partition(" ")
    if scheme.lower() != "bearer" or not raw:
        return None
    try:
        return AccessToken(raw)["role"]
    except (TokenError, KeyError):
        return None


class TuniGraphQLView(AsyncGraphQLView):
    async def dispatch(self, request, *args, **kwargs):
        if read_role(request) is None:
            return JsonResponse(
                {"errors": [{"message": "Authentication required"}]}, status=401
            )
        return await super().dispatch(request, *args, **kwargs)

    async def get_context(self, request, response):
        # Nouveaux loaders a CHAQUE requete (le cache est par requete)
        return {
            "request": request,
            "response": response,
            "role": read_role(request),
            "nodes_loader": DataLoader(load_fn=load_nodes),
            "anomalies_loader": DataLoader(load_fn=load_anomalies),
            "executions_loader": DataLoader(load_fn=load_executions),
            "receipts_loader": DataLoader(load_fn=load_receipts),
        }


urlpatterns = [
    path("", csrf_exempt(TuniGraphQLView.as_view(schema=schema))),
]
