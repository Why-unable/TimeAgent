from django.urls import path

from apps.external_data.views import ProviderCatalogView

urlpatterns = [path("catalog/", ProviderCatalogView.as_view(), name="provider-catalog")]
