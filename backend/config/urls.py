from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', include('tunisovereign_core.api_urls')),
    path('graphql/', include('tunisovereign_core.graphql_urls')),
]
