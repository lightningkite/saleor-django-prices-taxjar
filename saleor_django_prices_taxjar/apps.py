from django.apps import AppConfig
from django.conf import settings


class SaleorDjangoPricesTaxjarConfig(AppConfig):
    name = 'saleor-django-prices-taxjar.saleor_django_prices_taxjar'

    def ready(self):
        # from . import monkeypatch_tests
        from . import monkeypatches
        if getattr(settings, 'TAXJAR_SYNC_ORDERS', False):
            from . import signals
