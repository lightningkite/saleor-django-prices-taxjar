import importlib

# This is for TransactionRecords from django-payments-braintree-dropin
TransactionRecord = None
tried = False


def get_record_model():
    global TransactionRecord
    global tried
    if TransactionRecord is None and not tried:
        try:
            braintree_dropin_log_models = importlib.import_module(
                "django-payments-braintree-dropin.payments_braintree_dropin_log.models"
            )
            TransactionRecord = braintree_dropin_log_models.TransactionRecord
        except:
            tried = True

    return TransactionRecord
