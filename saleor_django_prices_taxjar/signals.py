import logging

from decimal import Decimal

from django.conf import settings
from django.db.models import Sum
from django.db.models.signals import post_save, pre_delete

import taxjar

from . import get_record_model

from saleor.order.models import Order, Payment, ZERO_TAXED_MONEY, PaymentStatus
from saleor.discount import VoucherType

logger = logging.getLogger(__name__)


client = taxjar.Client(api_key=settings.TAXJAR_ACCESS_KEY,
                       options={'timeout': 30})


TransactionRecord = get_record_model()


def create_taxjar_order_transaction(order):
    if not getattr(settings, 'TAXJAR_SYNC_ORDERS'):
        print('create_taxjar_order_transaction')
        return
    address = order.shipping_address or order.billing_address
    if (not address or not getattr(address, 'postal_code') or
            not getattr(address, 'country_area')):
        raise ValueError('Order has no address, which is required!')

    amount = order.total_net.amount
    shipping = order.shipping_price_net.amount
    if order.voucher and order.voucher.type == VoucherType.SHIPPING:
        # if the shipping was discounted reflect that in the record
        shipping -= getattr(order.discount_amount,
                            'amount', order.discount_amount)
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
    if not getattr(settings, 'TAXJAR_SYNC_ORDERS'):
        print('update_taxjar_order_transaction')
        return
    amount = order.total_net.amount
    shipping = order.shipping_price_net.amount
    if order.voucher and order.voucher.type == VoucherType.SHIPPING:
        # if the shipping was discounted reflect that in the record
        shipping -= getattr(order.discount_amount,
                            'amount', order.discount_amount)
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
    else:
        payment = order.get_last_payment()
        amount = order.total_net.amount
        if payment.status == PaymentStatus.CONFIRMED:
            amount = payment.get_captured_price().amount - sales_tax

    address = order.shipping_address or order.billing_address
    if (not address or not getattr(address, 'postal_code') or
            not getattr(address, 'country_area')):
        raise ValueError('Order has no address, which is required!')

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
            except ValueError as ve:
                # We have no address, so we can't add it
                logger.exception(
                    'TaxJar insert failed for order {} - no address'.format(
                        instance),
                    exc_info=ve,
                    extra={
                        'order': instance,
                        'shipping_address': getattr(
                            instance, 'shipping_address'),
                        'billing_address': getattr(
                            instance, 'billing_address'),
                    })
            except:
                update_taxjar_order_transaction(instance)
    except Exception as e:
        logger.exception(
            'TaxJar upsert failed for order {}'.format(instance),
            exc_info=e,
            extra={
                'order': instance,
                'shipping_address': getattr(instance, 'shipping_address'),
                'billing_address': getattr(instance, 'billing_address'),
            })


def handle_payment_save(sender, instance, *args, **kwargs):
    handle_order_save(sender, instance.order)


post_save.connect(handle_order_save, sender=Order)
pre_delete.connect(handle_order_save, sender=Order)
post_save.connect(handle_payment_save, sender=Payment)
pre_delete.connect(handle_payment_save, sender=Payment)

if TransactionRecord:
    def handle_transaction_record_save(sender, instance, *args, **kwargs):
        handle_payment_save(sender, instance.payment)

    post_save.connect(handle_transaction_record_save, sender=TransactionRecord)
    pre_delete.connect(handle_transaction_record_save,
                       sender=TransactionRecord)
