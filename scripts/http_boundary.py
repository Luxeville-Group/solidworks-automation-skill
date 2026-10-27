"""@brief HTTPS, redirect, and size boundaries for two fixed-origin downloaders; no new service."""
import urllib.error
import urllib.request
from urllib.parse import urlsplit


def validate_https_url(url, allowed_host):
    """@brief Validate the actual request origin; reject credentials, unexpected ports, fragments, and control characters.
    @param url Complete request URL.
    @param allowed_host Fixed host declared by caller code, never supplied by task input.
    @return Parsed SplitResult.
    """
    if not isinstance(url, str) or any(ord(char) <= 32 or char == "\\" for char in url):
        raise ValueError("İstek URL adresinde izin verilmeyen karakterler var")
    try:
        parts = urlsplit(url)
        allowed = parts.scheme == "https" and parts.hostname == allowed_host and parts.port in (None, 443)
    except ValueError as error:
        raise ValueError("İstek URL adresinin host veya port değeri geçersiz") from error
    if not allowed or parts.username is not None or parts.password is not None or parts.query or parts.fragment:
        raise ValueError("İstek sabit bir HTTPS kaynağı kullanmalı; kimlik bilgisi, query veya fragment içermemeli")
    return parts


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """@brief Fixed GraphQL/raw-commit requests must respond directly; never forward credentials through redirects."""
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise urllib.error.HTTPError(req.full_url, code, "Sabit kaynak isteklerinde yönlendirme yasak", headers, fp)


def read_https_response(request, *, allowed_host, max_bytes, timeout=30):
    """@brief Validate at the actual request boundary and bound reads so callers cannot bypass manifest preflight."""
    validate_https_url(request.full_url, allowed_host)
    if not isinstance(max_bytes, int) or max_bytes < 1:
        raise ValueError("Yanıt boyutu sınırı pozitif tamsayı olmalı")
    opener = urllib.request.build_opener(_NoRedirect())
    with opener.open(request, timeout=timeout) as response:
        length = response.headers.get("Content-Length")
        if length is not None and int(length) > max_bytes:
            raise ValueError("Yanıt boyut sınırını aşıyor")
        data = response.read(max_bytes + 1)
        if len(data) > max_bytes:
            raise ValueError("Yanıt boyut sınırını aşıyor")
        return data
