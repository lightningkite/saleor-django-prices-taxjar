from geolite2 import geolite2

from django.conf import settings

from prices import Money
from django_prices_taxjar import LineItem, DEFAULT_TAXJAR_PRODUCT_TAX_CODE
from django_prices_taxjar.models import TaxCategories
from django_prices_taxjar.utils import (
    get_taxes_for_order, get_tax_rates_for_region, get_tax_rate,
    get_tax_for_rate)

from saleor.core.utils.taxes import DEFAULT_TAX_RATE_NAME

georeader = geolite2.reader()

ORDER_TAX_RATE = 'ORDER_TAX_RATE'

ZERO_MONEY = Money(0, settings.DEFAULT_CURRENCY)


def get_country_region_by_ip(ip_address):
    geo_data = georeader.get(ip_address)
    if (geo_data and 'subdivisions' in geo_data and
            len(geo_data['subdivisions']) and
            'iso_code' in geo_data['subdivisions'][0] and
            'country' in geo_data and
            'iso_code' in geo_data['country']):
        return (geo_data['country']['iso_code'],
                geo_data['subdivisions'][0]['iso_code'])
    return (None, None)


def get_taxes_for_cart_full(cart, shipping_cost, discounts, default_taxes):
    country = cart.shipping_address.country.code
    postal_code = cart.shipping_address.postal_code
    region_code = cart.shipping_address.country_area
    city = cart.shipping_address.city
    street = cart.shipping_address.street_address_1
    kwargs = {}
    if getattr(settings, 'DJANGO_PRICES_TAXJAR_USE_LINE_ITEMS', True):
        if len(list(cart)):
            kwargs['line_items'] = map(lambda line: LineItem(
                line.variant.id,
                line.quantity,
                line.variant.base_price,
                (line.variant.product.tax_rate
                    if line.variant.product.tax_rate != DEFAULT_TAX_RATE_NAME
                 else DEFAULT_TAXJAR_PRODUCT_TAX_CODE),
                (line.variant.base_price - line.variant.get_price(
                    discounts, []).gross)), cart)
        else:
            kwargs['amount'] = ZERO_MONEY
    else:
        try:
            kwargs['amount'] = cart.get_subtotal(
                discounts, None).gross - cart.discount_amount

        # This can potentially throw a TypeError because the function
        # signature is different.
        except TypeError:
            kwargs['amount'] = cart.get_subtotal().gross - cart.discount_amount

    tax = get_taxes_for_order(
        shipping_cost.gross, country, postal_code, region_code, city, street,
        **kwargs)
    return tax


def get_taxes_for_country_region(country, region=None):
    if (country.code != 'CA' and country.code != 'US'):
        # TaxJar only has summaries with regions for CA and US.
        region = None
    tax_rates = get_tax_rates_for_region(country.code, region)
    if tax_rates is None:
        return None

    taxes = {
        DEFAULT_TAX_RATE_NAME: {
            'value': get_tax_rate(tax_rates),
            'tax': get_tax_for_rate(tax_rates),
        }
    }

    return taxes


def get_tax_rate_types():
    categories = TaxCategories.objects.singleton()
    if categories:
        return list(map(
            lambda category: (category['product_tax_code'], category['name']),
            categories.types))
    return []
