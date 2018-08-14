# saleor-django-prices-taxjar

Adapter for [Saleor](https://github.com/mirumee/saleor) and [django-prices-taxjar](https://github.com/722c/django-prices-taxjar).

This provides a (currently skeleton) implementation of an adapter between Saleor and django-prices-taxjar. This is currently built for the `v2018.6` tag of Saleor.

_This is primarily centered around monkeypatching existing Saleor code so that few changes need to be made to install this. This does make it more brittle, so please use at your own risk. Updating this should be pretty straightforward, however._

## Installation

To install, `pip install` the package as such:

```bash
pip install git+git://github.com/722c/saleor-django-prices-taxjar.git#egg='saleor-django-prices-taxjar'
```

Or list the package in your `requirements.txt` as such:

```
git+git://github.com/722c/saleor-django-prices-taxjar.git#egg='saleor-django-prices-taxjar'
```

Alternatively, this can be installed as a Git submodule directly in the root directory of your Saleor instance.

## Configuration

Once you have installed the app, you will need to add a few things to your project:

Add the app to your installed apps (you will want this at the bottom):

```python
INSTALLED_APPS = [
    ...

    # django-prices-taxjar stuff.
    'django_prices_taxjar',
    'saleor-django-prices-taxjar.saleor_django_prices_taxjar.apps.SaleorDjangoPricesTaxjarConfig',
]
```

You will then want to add the middleware from this app and disable the stock taxes middleware from Saleor. The middleware for region will need to be after the stock Saleor middleware for country, as we use that for validation.

```python
MIDDLEWARE = [
    ...

    'saleor.core.middleware.country',
    # Middleware to add request.region from the source IP address.
    'saleor-django-prices-taxjar.saleor_django_prices_taxjar.middleware.region',

    ...

    # Middleware for handling taxes
    # 'saleor.core.middleware.taxes',  # This should be disabled by commenting out or removing.
    'saleor-django-prices-taxjar.saleor_django_prices_taxjar.middleware.taxes',

    ...
]
```

Finally, you will need to add you TaxJar API Access Key/Token to your settings:

```python
TAXJAR_ACCESS_KEY = os.environ.get('TAXJAR_ACCESS_KEY')
```
