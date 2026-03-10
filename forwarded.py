from typing import Any

from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware


def _is_trusted_proxy(client_host: str | None, trusted_hosts: str) -> bool:
    if trusted_hosts == "*":
        return True
    return client_host in {host.strip() for host in trusted_hosts.split(",") if host.strip()}


class ForwardedHostMiddleware:
    def __init__(self, app: Any, *, trusted_hosts: str) -> None:
        self.app = app
        self.trusted_hosts = trusted_hosts

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] == "lifespan":
            return await self.app(scope, receive, send)

        client = scope.get("client")
        client_host = client[0] if client else None
        if not _is_trusted_proxy(client_host, self.trusted_hosts):
            return await self.app(scope, receive, send)

        headers = list(scope["headers"])
        forwarded_host = next(
            (
                value.decode("latin-1").split(",", 1)[0].strip()
                for key, value in headers
                if key == b"x-forwarded-host"
            ),
            "",
        )
        if forwarded_host:
            scope = {
                **scope,
                "headers": [
                    (key, value)
                    for key, value in headers
                    if key != b"host"
                ] + [(b"host", forwarded_host.encode("latin-1"))],
            }

        return await self.app(scope, receive, send)


def wrap_proxy_headers(app: Any, *, trusted_hosts: str) -> Any:
    return ForwardedHostMiddleware(
        ProxyHeadersMiddleware(app, trusted_hosts=trusted_hosts),
        trusted_hosts=trusted_hosts,
    )
