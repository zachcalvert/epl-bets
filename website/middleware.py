from django.conf import settings
from django.http import HttpResponsePermanentRedirect, HttpResponseRedirect


class CanonicalHostMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        canonical_host = settings.CANONICAL_HOST

        if not settings.DEBUG and canonical_host:
            request_host = request.get_host().split(":", 1)[0]
            if request_host == f"www.{canonical_host}":
                url = f"https://{canonical_host}{request.get_full_path()}"
                if request.method in ("GET", "HEAD"):
                    return HttpResponsePermanentRedirect(url)
                return HttpResponseRedirect(url)

        return self.get_response(request)
