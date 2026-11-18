from django.urls import path
from strawberry.django.views import AsyncGraphQLView
from strawberry.dataloader import DataLoader

from .graphql_schema import schema, load_nodes, load_anomalies


class TuniGraphQLView(AsyncGraphQLView):
    async def get_context(self, request, response):
        # Nouveaux loaders a CHAQUE requete (le cache est par requete)
        return {
            "request": request,
            "response": response,
            "nodes_loader": DataLoader(load_fn=load_nodes),
            "anomalies_loader": DataLoader(load_fn=load_anomalies),
        }


urlpatterns = [path("", TuniGraphQLView.as_view(schema=schema))]
