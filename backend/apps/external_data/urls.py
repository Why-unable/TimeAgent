from django.urls import path

from apps.external_data.views import LocationSearchView, ProviderCatalogView

urlpatterns = [
    path("catalog/", ProviderCatalogView.as_view(), name="provider-catalog"),
    path("locations/", LocationSearchView.as_view(), name="location-search"),
]
