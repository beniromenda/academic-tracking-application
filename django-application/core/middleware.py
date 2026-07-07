from django.utils.cache import add_never_cache_headers


class DisableClientSideCacheMiddleware:
    """Prevent browser caching of dynamic app pages to avoid back-button access after logout."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)

        # Skip static/admin asset paths and only enforce on app/auth pages.
        if request.path.startswith('/static/') or request.path.startswith('/media/'):
            return response

        add_never_cache_headers(response)
        response['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
        response['Pragma'] = 'no-cache'
        response['Expires'] = '0'
        return response
