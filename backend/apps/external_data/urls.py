from django.urls import path

from apps.external_data.views import (
    AdministrativeAreaView,
    AdministrativeLocationResolveView,
    CurrentLocationView,
    LocationSearchView,
    ProviderCatalogView,
)

urlpatterns = [
    path("catalog/", ProviderCatalogView.as_view(), name="provider-catalog"),
    path("locations/", LocationSearchView.as_view(), name="location-search"),
    path(
        "locations/administrative-areas/",
        AdministrativeAreaView.as_view(),
        name="administrative-areas",
    ),
    path("locations/current/", CurrentLocationView.as_view(), name="current-location"),
    path(
        "locations/resolve/",
        AdministrativeLocationResolveView.as_view(),
        name="administrative-location-resolve",
    ),
]
