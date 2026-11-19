from django.urls import path

from apps.panel_api.views import ApiCatalogView, ApiTokenDetailView, ApiTokenListCreateView

urlpatterns = [
    path("", ApiTokenListCreateView.as_view(), name="api-token-list"),
    path("catalog/", ApiCatalogView.as_view(), name="api-token-catalog"),
    path("<int:pk>/", ApiTokenDetailView.as_view(), name="api-token-detail"),
]
