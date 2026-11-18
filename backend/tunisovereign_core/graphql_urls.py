from django.urls import path
from django.views.decorators.csrf import csrf_exempt
from strawberry.django.views import AsyncGraphQLView
from strawberry.dataloader import DataLoader

from .graphql_schema import schema, load_nodes, load_anomalies, load_receipts


class TuniGraphQLView(AsyncGraphQLView):
    async def get_context(self, request, response):
        # Nouveaux loaders a CHAQUE requete (le cache est par requete)
        return {
            "request": request,
            "response": response,
            "nodes_loader": DataLoader(load_fn=load_nodes),
            "anomalies_loader": DataLoader(load_fn=load_anomalies),
            "receipts_loader": DataLoader(load_fn=load_receipts),
        }


urlpatterns = [
    path("", csrf_exempt(TuniGraphQLView.as_view(schema=schema))),
]
