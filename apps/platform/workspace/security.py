from ipaddress import ip_address


def client_ip(request):
    """Trust Cloudflare's overwritten client header only on the local origin hop."""
    remote = request.META.get('REMOTE_ADDR', '')
    candidate = request.META.get('HTTP_CF_CONNECTING_IP', remote) if remote in ('127.0.0.1', '::1') else remote
    try:
        return str(ip_address(candidate))
    except ValueError:
        return None
