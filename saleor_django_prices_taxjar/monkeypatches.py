# This file exists to monkey patch in taxjar in saleor code.

import logging

from django.conf import settings

from django_countries.fields import Country

from prices import Money, TaxedMoney

from saleor.checkout import utils as checkout_utils
from saleor.checkout.models import Cart
from saleor.dashboard.product import forms as dashboard_product_forms
from saleor.core.utils import taxes
from saleor.order import utils as order_utils

from .utils import (get_taxes_for_country_region, get_taxes_for_cart_full,
                    get_tax_rate_types)


logger = logging.getLogger(__name__)


def get_taxes_for_cart(cart, default_taxes):
    """Return taxes (if handled) due to shipping address or default one."""
    if not settings.TAXJAR_ACCESS_KEY:
        return None

    if cart.shipping_address:
        taxes = get_taxes_for_country_region(
            cart.shipping_address.country,
            cart.shipping_address.country_area)
        return taxes

    return default_taxes


checkout_utils.get_taxes_for_cart = get_taxes_for_cart


def get_taxes_for_address(address):
    if address is not None:
        country = address.country
        region = address.country_area
    else:
        country = Country(settings.DEFAULT_COUNTRY)
        region = None
    return get_taxes_for_country_region(country, region)


taxes.get_taxes_for_address = get_taxes_for_address


def get_taxes_for_country(country):
    return get_taxes_for_country_region(country, None)


taxes.get_taxes_for_country = get_taxes_for_country


def get_total(cart, discounts=None, taxes=None):
    """
    Return the total cost of the cart.

    This is overridden so that we don't use default taxes and use taxes for
    the order as a whole.
    """
    if cart.shipping_address and len(cart):
        try:
            tax = get_taxes_for_cart_full(
                cart, cart.get_shipping_price(None), discounts, None)
            return tax(cart.get_subtotal(discounts, None) +
                       cart.get_shipping_price(None) -
                       cart.discount_amount)
        except Exception as e:
            logger.error('Failed to compute tax.', exc_info=e)
    return (cart.get_subtotal(discounts, taxes) +
            cart.get_shipping_price(taxes) -
            cart.discount_amount)


Cart.get_total = get_total


def get_tax_rate_type_choices():
    rate_types = [('', '')] + get_tax_rate_types()
    return sorted(rate_types, key=lambda x: x[0])


dashboard_product_forms.get_tax_rate_type_choices = get_tax_rate_type_choices


@order_utils.update_voucher_discount
def recalculate_order(order, **kwargs):
    """
    Recalculate and assign the total price of order.

    This will take into account tax from django_prices_taxjar.

    Total price is a sum of items in order and order shipping price minus
    discount amount.

    Voucher discount amount is recalculated by default. To avoid this, pass
    update_voucher_discount argument set to False.
    """
    # avoid using prefetched order lines
    lines = [order_utils.OrderLine.objects.get(pk=line.pk) for line in order]
    prices = [line.get_total() for line in lines]
    total = sum(prices, order.shipping_price)
    # discount amount can't be greater than order total
    order.discount_amount = min(order.discount_amount, total.gross)
    if order.discount_amount:
        total -= order.discount_amount

    if order.shipping_method:
        order.shipping_price = order.shipping_method.get_total_price(
            number_of_items=sum([line.quantity for line in lines]))

    if order.shipping_address:
        tax = get_taxes_for_cart_full(order, order.shipping_price, [], [])
        order.total = tax(total)
    else:
        order.total = total

    order.save()


order_utils.recalculate_order = recalculate_order


def update_order_prices(order, discounts):
    """
    Update prices in order with given discounts.

    Overridden to prevent taxes from being applied at the line level.
    """
    taxes = []

    for line in order:
        if line.variant:
            line.unit_price = line.variant.get_price(discounts, taxes)
            line.sale_amount = line.unit_price.gross.amount - line.variant.get_price(discounts, taxes).gross.amount
            if line.sale_amount > 0:
                line.used_sale = True
            else:
                line.used_sale = False
            line.tax_rate = order_utils.get_tax_rate_by_name(
                line.variant.product.tax_rate, taxes)
            line.save()

    if order.shipping_method:
        order.shipping_price = order.shipping_method.get_total_price(
            taxes, number_of_items=order.get_total_quantity())
        order.save()

    recalculate_order(order)


order_utils.update_order_prices = update_order_prices


def add_variant_to_order(order, variant, quantity, discounts=None, taxes=None, used_sale=False, voucher=None, used_voucher=False):
    """
    Add total_quantity of variant to order.

    Raises InsufficientStock exception if quantity could not be fulfilled.

    Overridden to prevent taxes from being applied at the line level.
    """
    variant.check_quantity(quantity)
    
    line = order.lines.filter(variant=variant, used_voucher=used_voucher).first()
    if line:
        line = order.lines.get(variant=variant)
        line.quantity += quantity
        if used_sale:
            line.used_sale = True
            line.save(update_fields=['quantity', 'used_sale'])
        elif used_voucher:
            line.used_voucher = True
            line.save(update_fields=['quantity', 'used_voucher'])
        else:
            line.save(update_fields=['quantity'])
    else:
        unit_price = variant.get_price()
        price = variant.get_price(discounts, voucher=voucher, subtotal=False)
        order.lines.create(
            product_name=variant.display_product(),
            product_sku=variant.sku,
            is_shipping_required=variant.is_shipping_required(),
            quantity=quantity,
            variant=variant,
            unit_price=unit_price,
            sale_amount=unit_price.gross.amount - price.gross.amount if used_sale else 0,
            voucher_amount = unit_price.gross.amount - price.gross.amount if used_voucher else 0,
            tax_rate=order_utils.get_tax_rate_by_name(
                variant.product.tax_rate, []),
            used_sale=used_sale,
            used_voucher=used_voucher)

    if variant.track_inventory:
        order_utils.allocate_stock(variant, quantity)


order_utils.add_variant_to_order = add_variant_to_order
