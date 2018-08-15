from tests import * as tests


def compare_taxes(*args):
    """
    Disable the comparing of taxes for tests.

    The tests are all built around Vatlayer, so they are inherently invalid.
    """
    pass


tests.utils.compare_taxes = compare_taxes


def test_view_cart_with_taxes(settings, client, sale, request_cart_with_item,
                              vatlayer):
    """
    Disable this test since it is built around Vatlayer and is invalid.
    """
    pass


tests.test_cart.test_view_cart_with_taxes = test_view_cart_with_taxes


def test_cart_summary_page(settings, client, request_cart_with_item, vatlayer):
    """
    Remove stuff about taxes since it is built around Vatlayer.

    Because it is built around Vatlayer, it is inherently invalid.
    """
    settings.DEFAULT_COUNTRY = 'PL'
    response = client.get(tests.test_cart.reverse('cart:summary'))
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


tests.test_cart.test_cart_summary_page = test_cart_summary_page


def test_add_variant_to_order_adds_line_for_new_variant(
        order_with_lines, product, taxes):
    """
    Remove stuff about taxes since it is built around Vatlayer.

    Because it is built around Vatlayer, it is inherently invalid.
    """
    order = order_with_lines
    variant = product.variants.get()
    lines_before = order.lines.count()

    tests.test_order.add_variant_to_order(order, variant, 1, taxes=None)

    line = order.lines.last()
    assert order.lines.count() == lines_before + 1
    assert line.product_sku == variant.sku
    assert line.quantity == 1
    assert line.unit_price == TaxedMoney(
        net=Money(10, 'USD'), gross=Money(10, 'USD'))


tests.test_order.test_add_variant_to_order_adds_line_for_new_variant = (
    test_add_variant_to_order_adds_line_for_new_variant)


def test_view_order_shipping_edit(
        admin_client, draft_order, shipping_method, settings, vatlayer):
    """
    Remove stuff about taxes since it is built around Vatlayer.

    Because it is built around Vatlayer, it is inherently invalid.
    """
    method = shipping_method.price_per_country.create(
        price=Money(5, settings.DEFAULT_CURRENCY), country_code='PL')
    url = tests.dashboard.test_order.reverse(
        'dashboard:order-shipping-edit', kwargs={'order_pk': draft_order.pk})
    data = {'shipping_method': method.pk}

    response = admin_client.post(url, data)

    assert response.status_code == 302
    redirect_url = tests.dashboard.test_order.reverse(
        'dashboard:order-details', kwargs={'order_pk': draft_order.pk})
    assert tests.dashboard.test_order.get_redirect_location(
        response) == redirect_url
    draft_order.refresh_from_db()
    assert draft_order.shipping_method_name == shipping_method.name
    assert draft_order.shipping_price == method.get_total_price(taxes=None)
    assert draft_order.shipping_method == method


tests.dashboard.test_order.test_view_order_shipping_edit = (
    test_view_order_shipping_edit)


def test_product_form_sanitize_product_description(
        product_type, default_category):
    """Change the products tax_rate to match a TaxJar one."""
    product = tests.dashboard.test_product.Product.objects.create(
        name='Test Product', price=10, description='', pk=10,
        product_type=product_type, category=default_category)
    data = tests.dashboard.test_product.model_to_dict(product)
    data['tax_rate'] = ''
    data['description'] = (
        '<b>bold</b><p><i>italic</i></p><h2>Header</h2><h3>subheader</h3>'
        '<blockquote>quote</blockquote>'
        '<p><a href="www.mirumee.com">link</a></p>'
        '<p>an <script>evil()</script>example</p>')
    data['price'] = 20

    form = tests.dashboard.test_product.ProductForm(data, instance=product)
    assert form.is_valid()

    form.save()
    assert product.description == (
        '<b>bold</b><p><i>italic</i></p><h2>Header</h2><h3>subheader</h3>'
        '<blockquote>quote</blockquote>'
        '<p><a href="www.mirumee.com">link</a></p>'
        '<p>an &lt;script&gt;evil()&lt;/script&gt;example</p>')
    assert product.seo_description == (
        'bolditalicHeadersubheaderquotelinkan evil()example')


tests.dashboard.test_product.test_product_form_sanitize_product_description = (
    test_product_form_sanitize_product_description)


def test_product_form_seo_description(unavailable_product):
    """Change the products tax_rate to match a TaxJar one."""
    seo_description = (
        'This is a dummy product. '
        'HTML <b>shouldn\'t be removed</b> since it\'s a simple text field.')
    data = tests.dashboard.test_product.model_to_dict(unavailable_product)
    data['tax_rate'] = ''
    data['price'] = 20
    data['description'] = 'a description'
    data['seo_description'] = seo_description

    form = tests.dashboard.test_product.ProductForm(
        data, instance=unavailable_product)
    assert form.is_valid()

    form.save()
    assert unavailable_product.seo_description == seo_description


tests.dashboard.test_product.test_product_form_seo_description = (
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

    data = tests.dashboard.test_product.model_to_dict(unavailable_product)
    data['tax_rate'] = ''
    data['price'] = 20
    data['description'] = description

    form = tests.dashboard.test_product.ProductForm(
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


tests.dashboard.test_product.test_product_form_seo_description_too_long = (
    test_product_form_seo_description_too_long)


def test_view_tax_details(*args):
    """
    Disable the testing of viewing taxes.

    The test is built around Vatlayer, so it is inherently invalid.
    """
    pass


tests.dashboard.test_taxes.test_view_tax_details = test_view_tax_details
