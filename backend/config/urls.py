from django.contrib import admin
from django.urls import path, include
from rest_framework_simplejwt.views import TokenRefreshView
from tunisovereign_core.api_rest import RegisterView, SovereignTokenObtainPairView

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/auth/register/", RegisterView.as_view()),
    path("api/auth/login/", SovereignTokenObtainPairView.as_view()),
    path("api/auth/refresh/", TokenRefreshView.as_view()),
    path("", include("tunisovereign_core.api_urls")),
    path("graphql/", include("tunisovereign_core.graphql_urls")),
]