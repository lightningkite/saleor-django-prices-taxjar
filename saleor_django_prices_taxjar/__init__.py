import importlib

# This is for TransactionRecords from django-payments-braintree-dropin
TransactionRecord = None


def get_record_model():
    global TransactionRecord
    if TransactionRecord is None:
        from saleor.core.permissions import MODELS_PERMISSIONS
