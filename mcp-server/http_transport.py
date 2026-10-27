"""@brief Optional HTTP transport for the same MCP server with explicit Host/Origin and shared-secret boundaries."""
import hmac


class TokenAuthMiddleware:
    """@brief Validate Bearer at the HTTP layer without changing tool schemas, COM locks, or logs."""
    def __init__(self, app, token):
        self.app = app
        self.expected = ("Bearer " + token).encode("utf-8") if token else None

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http" and self.expected is not None:
            supplied = dict(scope.get("headers", [])).get(b"authorization", b"")
            if not hmac.compare_digest(supplied, self.expected):
                await send({"type": "http.response.start", "status": 401,
                    "headers": [(b"content-type", b"text/plain"), (b"www-authenticate", b"Bearer realm=solidworks")]})
                await send({"type": "http.response.body", "body": b"Unauthorized"})
                return
        await self.app(scope, receive, send)
