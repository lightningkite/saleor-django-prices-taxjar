import logging

from decimal import Decimal

from django.conf import settings
from django.db.models import Sum
from django.db.models.signals import post_save, pre_delete

import taxjar

from . import get_record_model

from saleor.order.models import Order, Payment, ZERO_TAXED_MONEY, PaymentStatus


logger = logging.getLogger(__name__)


client = taxjar.Client(api_key=settings.TAXJAR_ACCESS_KEY,
                       options={'timeout': 30})


TransactionRecord = get_record_model()


def create_taxjar_order_transaction(order):
    if settings.DEBUG:
        print('create_taxjar_order_transaction')
        return
    address = order.shipping_address or order.billing_address
    if not address:
        raise ValueError('Order has no address, which is required!')

    amount = order.total_net.amount
    shipping = order.shipping_price_net.amount
    if order.voucher and order.voucher.type == VoucherType.SHIPPING:
        # if the shipping was discounted reflect that in the record
        shipping -= order.discount_amount
    sales_tax = order.total.tax.amount
    if TransactionRecord:
        records = TransactionRecord.objects.filter(
            status=PaymentStatus.REFUNDED, payment__order=order)
        if records.exists():
            refunded_amounts = records.aggregate(
                Sum('primary'), Sum('tax'), Sum('delivery'), Sum('discount'))
            amount = amount - \
                refunded_amounts['primary__sum'] - \
                refunded_amounts['delivery__sum'] - \
                refunded_amounts['discount__sum']
            shipping = shipping - refunded_amounts['delivery__sum']
            sales_tax = sales_tax - refunded_amounts['tax__sum']
        else:
            payment = order.get_last_payment()
            amount = order.total_net.amount
            if payment.status == PaymentStatus.CONFIRMED:
                amount = payment.get_captured_price().amount - sales_tax

    taxjar_order = client.create_order({
        'transaction_id': str(order.id),
        'transaction_date': order.created.isoformat(),
        'to_country': address.country.code,
        'to_zip': address.postal_code,
        'to_state': address.country_area,
        'to_city': address.city,  # optional
        'to_street': address.street_address_1,  # optional
        # with shipping but without tax
        'amount': float(amount),
        'shipping': float(shipping),  # without tax
        'sales_tax': float(sales_tax),  # total tax for order
    })


def update_taxjar_order_transaction(order):
    if settings.DEBUG:
        print('update_taxjar_order_transaction')
        return
    amount = order.total_net.amount
    shipping = order.shipping_price_net.amount
    sales_tax = order.total.tax.amount
    if TransactionRecord:
        records = TransactionRecord.objects.filter(
            status=PaymentStatus.REFUNDED, payment__order=order)
        if records.exists():
            refunded_amounts = records.aggregate(
                Sum('primary'), Sum('tax'), Sum('delivery'), Sum('discount'))
            amount = amount - \
                refunded_amounts['primary__sum'] - \
                refunded_amounts['delivery__sum'] - \
                refunded_amounts['discount__sum']
            shipping = shipping - refunded_amounts['delivery__sum']
            sales_tax = sales_tax - refunded_amounts['tax__sum']
        else:
            payment = order.get_last_payment()
            amount = order.total_net.amount
            if payment.status == PaymentStatus.CONFIRMED:
                amount = payment.get_captured_price().amount - sales_tax

    taxjar_order = client.update_order(str(order.id), {
        'transaction_id': str(order.id),
        # with shipping but without tax
        'amount': float(amount),
        'shipping': float(shipping),  # without tax
        'sales_tax': float(sales_tax),  # total tax for order
    })


def handle_order_save(sender, instance, *args, **kwargs):
    try:
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
    except:
        logger.exception('TaxJar upsert failed for order {}'.format(instance))


def handle_payment_save(sender, instance, *args, **kwargs):
    handle_order_save(sender, instance.order)


post_save.connect(handle_order_save, sender=Order)
pre_delete.connect(handle_order_save, sender=Order)
post_save.connect(handle_payment_save, sender=Payment)
pre_delete.connect(handle_payment_save, sender=Payment)
