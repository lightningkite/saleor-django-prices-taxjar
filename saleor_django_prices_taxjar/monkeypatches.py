# This file exists to monkey patch in taxjar in saleor code.

from django.conf import settings

from django_countries.fields import Country

from prices import Money, TaxedMoney

from saleor.checkout import utils as checkout_utils
from saleor.checkout.models import Cart
from saleor.dashboard.product import forms as dashboard_product_forms
from saleor.core.utils import taxes
from saleor.order import utils as order_utils

from tests import test_cart
from tests import test_order
from tests import utils as test_utils
from tests.dashboard import test_order as dashboard_test_order
from tests.dashboard import test_product as dashboard_test_product
from tests.dashboard import test_taxes as dashboard_test_taxes

from .utils import (get_taxes_for_country_region, get_taxes_for_cart_full,
                    get_tax_rate_types)


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
        tax = get_taxes_for_cart_full(
            cart, cart.get_shipping_price(None), discounts, None)
        return tax(cart.get_subtotal(discounts, None) +
                   cart.get_shipping_price(None) -
                   cart.discount_amount)
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
            line.tax_rate = order_utils.get_tax_rate_by_name(
                line.variant.product.tax_rate, taxes)
            line.save()

    if order.shipping_method:
        order.shipping_price = order.shipping_method.get_total_price(taxes)
        order.save()

    recalculate_order(order)


order_utils.update_order_prices = update_order_prices


def add_variant_to_order(order, variant, quantity, discounts=None, taxes=None):
    """
    Add total_quantity of variant to order.

    Raises InsufficientStock exception if quantity could not be fulfilled.

    Overridden to prevent taxes from being applied at the line level.
    """
    variant.check_quantity(quantity)

    try:
        line = order.lines.get(variant=variant)
        line.quantity += quantity
        line.save(update_fields=['quantity'])
    except order_utils.OrderLine.DoesNotExist:
        order.lines.create(
            product_name=variant.display_product(),
            product_sku=variant.sku,
            is_shipping_required=variant.is_shipping_required(),
            quantity=quantity,
            variant=variant,
            unit_price=variant.get_price(discounts, []),
            tax_rate=order_utils.get_tax_rate_by_name(
                variant.product.tax_rate, []))

    if variant.track_inventory:
        order_utils.allocate_stock(variant, quantity)


order_utils.add_variant_to_order = add_variant_to_order


def compare_taxes(*args):
    """
    Disable the comparing of taxes for tests.

    The tests are all built around Vatlayer, so they are inherently invalid.
    """
    pass


test_utils.compare_taxes = compare_taxes


def test_view_cart_with_taxes(settings, client, sale, request_cart_with_item,
                              vatlayer):
    """
    Disable this test since it is built around Vatlayer and is invalid.
    """


test_cart.test_view_cart_with_taxes = test_view_cart_with_taxes


def test_cart_summary_page(settings, client, request_cart_with_item, vatlayer):
    """
    Remove stuff about taxes since it is built around Vatlayer.

    Because it is built around Vatlayer, it is inherently invalid.
    """
    settings.DEFAULT_COUNTRY = 'PL'
    response = client.get(test_cart.reverse('cart:summary'))
    assert response.status_code == 200
    content = response.context
    assert content['quantity'] == request_cart_with_item.quantity
    cart_total = request_cart_with_item.get_subtotal(taxes=None)
    assert content['total'] == cart_total
    assert len(content['lines']) == 1
    cart_line = content['lines'][0]
    variant = request_cart_with_item.lines.get().variant
    assert cart_line['variant'] == variant.name
    assert cart_line['quantity'] == 1


test_cart.test_cart_summary_page = test_cart_summary_page


def test_add_variant_to_order_adds_line_for_new_variant(
        order_with_lines, product, taxes):
    """
    Remove stuff about taxes since it is built around Vatlayer.

    Because it is built around Vatlayer, it is inherently invalid.
    """
    order = order_with_lines
    variant = product.variants.get()
    lines_before = order.lines.count()

    test_order.add_variant_to_order(order, variant, 1, taxes=None)

    line = order.lines.last()
    assert order.lines.count() == lines_before + 1
    assert line.product_sku == variant.sku
    assert line.quantity == 1
    assert line.unit_price == TaxedMoney(
        net=Money(10, 'USD'), gross=Money(10, 'USD'))


test_order.test_add_variant_to_order_adds_line_for_new_variant = (
    test_add_variant_to_order_adds_line_for_new_variant)


def test_view_order_shipping_edit(
        admin_client, draft_order, shipping_method, settings, vatlayer):
    """
    Remove stuff about taxes since it is built around Vatlayer.

    Because it is built around Vatlayer, it is inherently invalid.
    """
    method = shipping_method.price_per_country.create(
        price=Money(5, settings.DEFAULT_CURRENCY), country_code='PL')
    url = dashboard_test_order.reverse(
        'dashboard:order-shipping-edit', kwargs={'order_pk': draft_order.pk})
    data = {'shipping_method': method.pk}

    response = admin_client.post(url, data)

    assert response.status_code == 302
    redirect_url = dashboard_test_order.reverse(
        'dashboard:order-details', kwargs={'order_pk': draft_order.pk})
    assert dashboard_test_order.get_redirect_location(response) == redirect_url
    draft_order.refresh_from_db()
    assert draft_order.shipping_method_name == shipping_method.name
    assert draft_order.shipping_price == method.get_total_price(taxes=None)
    assert draft_order.shipping_method == method


dashboard_test_order.test_view_order_shipping_edit = (
    test_view_order_shipping_edit)


def test_product_form_sanitize_product_description(
        product_type, default_category):
    """Change the products tax_rate to match a TaxJar one."""
    product = dashboard_test_product.Product.objects.create(
        name='Test Product', price=10, description='', pk=10,
        product_type=product_type, category=default_category)
    data = dashboard_test_product.model_to_dict(product)
    data['tax_rate'] = ''
    data['description'] = (
        '<b>bold</b><p><i>italic</i></p><h2>Header</h2><h3>subheader</h3>'
        '<blockquote>quote</blockquote>'
        '<p><a href="www.mirumee.com">link</a></p>'
        '<p>an <script>evil()</script>example</p>')
    data['price'] = 20

    form = dashboard_test_product.ProductForm(data, instance=product)
    assert form.is_valid()

    form.save()
    assert product.description == (
        '<b>bold</b><p><i>italic</i></p><h2>Header</h2><h3>subheader</h3>'
        '<blockquote>quote</blockquote>'
        '<p><a href="www.mirumee.com">link</a></p>'
        '<p>an &lt;script&gt;evil()&lt;/script&gt;example</p>')
    assert product.seo_description == (
        'bolditalicHeadersubheaderquotelinkan evil()example')


dashboard_test_product.test_product_form_sanitize_product_description = (
    test_product_form_sanitize_product_description)


def test_product_form_seo_description(unavailable_product):
    """Change the products tax_rate to match a TaxJar one."""
    seo_description = (
        'This is a dummy product. '
        'HTML <b>shouldn\'t be removed</b> since it\'s a simple text field.')
    data = dashboard_test_product.model_to_dict(unavailable_product)
    data['tax_rate'] = ''
    data['price'] = 20
    data['description'] = 'a description'
    data['seo_description'] = seo_description

    form = dashboard_test_product.ProductForm(
        data, instance=unavailable_product)
    assert form.is_valid()

    form.save()
    assert unavailable_product.seo_description == seo_description


dashboard_test_product.test_product_form_seo_description = (
    test_product_form_seo_description)


def test_product_form_seo_description_too_long(unavailable_product):
    """Change the products tax_rate to match a TaxJar one."""
    description = (
        'Saying it fourth made saw light bring beginning kind over herb '
        'won\'t creepeth multiply dry rule divided fish herb cattle greater '
        'fly divided midst, gathering can\'t moveth seed greater subdue. '
        'Lesser meat living fowl called. Dry don\'t wherein. Doesn\'t above '
        'form sixth. Image moving earth without forth light whales. Seas '
        'were first form fruit that form they\'re, shall air. And. Good of'
        'signs darkness be place. Was. Is form it. Whose. Herb signs stars '
        'fill own fruit wherein. '
        'Don\'t set man face living fifth Thing the whales were. '
        'You fish kind. '
        'Them, his under wherein place first you night gathering.')

    data = dashboard_test_product.model_to_dict(unavailable_product)
    data['tax_rate'] = ''
    data['price'] = 20
    data['description'] = description

    form = dashboard_test_product.ProductForm(
        data, instance=unavailable_product)
    assert form.is_valid()

    form.save()
    assert len(unavailable_product.seo_description) <= 300
    assert unavailable_product.seo_description == (
        'Saying it fourth made saw light bring beginning kind over herb '
        'won\'t creepeth multiply dry rule divided fish herb cattle greater '
        'fly divided midst, gathering can\'t moveth seed greater subdue. '
        'Lesser meat living fowl called. Dry don\'t wherein. Doesn\'t above '
        'form sixth. Image moving earth without f...')


dashboard_test_product.test_product_form_seo_description_too_long = (
    test_product_form_seo_description_too_long)


def test_view_tax_details(*args):
    """
    Disable the testing of viewing taxes.

    The test is built around Vatlayer, so it is inherently invalid.
    """
    pass


dashboard_test_taxes.test_view_tax_details = test_view_tax_details
