from django.conf import settings
from django.utils.functional import SimpleLazyObject


from saleor.core.utils import get_client_ip

from .utils import get_country_region_by_ip, get_taxes_for_country_region


def region(get_response):
    """
    Detect the user's region and assign it to `request.region`.

    `request.region` will be None if there is no subdivisions[0].iso_code
    returned by geolite2 or if `request.country` is None or the country in
    geolite2's data does not match the current `request.country`.

    """
    def middleware(request):
        client_ip = get_client_ip(request)
        request.region = None
        if client_ip and request.country:
            country, region = get_country_region_by_ip(client_ip)
            # If `request.country` doesn't match the one returned by geolite2,
            # then the region doesn't exist in the country, so don't set it.
            if country == request.country:
                request.region = region
        return get_response(request)

    return middleware


def taxes(get_response):
    """Assign tax rates for country and region to `request.taxes`."""
    def middleware(request):
        if settings.TAXJAR_ACCESS_KEY:
            request.taxes = SimpleLazyObject(
                lambda: get_taxes_for_country_region(request.country,
                                                     request.region))
        else:
            request.taxes = None
        return get_response(request)

    return middleware
