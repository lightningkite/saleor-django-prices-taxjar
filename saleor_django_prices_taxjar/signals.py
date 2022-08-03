from django.conf import settings
from django.db.models.signals import post_save, pre_delete

import taxjar

from saleor.order.models import Order, Payment, ZERO_TAXED_MONEY, PaymentStatus


client = taxjar.Client(api_key=settings.TAXJAR_ACCESS_KEY)
client.set_api_config('headers', {
  'x-api-version': '2022-01-24'
})

def create_taxjar_order_transaction(order):
    address = order.shipping_address or order.billing_address
    if not address:
        raise ValueError('Order has no address, which is required!')
    taxjar_order = client.create_order({
        'transaction_id': str(order.id),
        'transaction_date': order.created.isoformat(),
        'to_country': address.country.code,
        'to_zip': address.postal_code,
        'to_state': address.country_area,
        'to_city': address.city,  # optional
        'to_street': address.street_address_1,  # optional
        # with shipping but without tax
        'amount': float(order.total_net.amount),
        'shipping': float(order.shipping_price_net.amount),  # without tax
        'sales_tax': float(order.total.tax.amount),  # total tax for order
    })


def update_taxjar_order_transaction(order):
    taxjar_order = client.update_order(str(order.id), {
        'transaction_id': str(order.id),
        # with shipping but without tax
        'amount': float(order.total_net.amount),
        'shipping': float(order.shipping_price_net.amount),  # without tax
        'sales_tax': float(order.total.tax.amount),  # total tax for order
    })


def handle_order_save(sender, instance, *args, **kwargs):
    total_paid = sum([
        payment.get_total_price() for payment in
        instance.payments.filter(status__in=[
            PaymentStatus.CONFIRMED,
            PaymentStatus.PREAUTH,
            PaymentStatus.REFUNDED,
        ])],
        ZERO_TAXED_MONEY)
    if total_paid.gross >= instance.total.gross:
        try:
            create_taxjar_order_transaction(instance)
        except ValueError:
            # We have no address, so we can't add it
            pass
        except:
            update_taxjar_order_transaction(instance)


def handle_payment_save(sender, instance, *args, **kwargs):
    handle_order_save(sender, instance.order)


post_save.connect(handle_order_save, sender=Order)
pre_delete.connect(handle_order_save, sender=Order)
post_save.connect(handle_payment_save, sender=Payment)
pre_delete.connect(handle_payment_save, sender=Payment)
