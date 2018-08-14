from django.apps import AppConfig


class SaleorDjangoPricesTaxjarConfig(AppConfig):
    name = 'saleor-django-prices-taxjar.saleor_django_prices_taxjar'

    def ready(self):
        from . import monkeypatches
