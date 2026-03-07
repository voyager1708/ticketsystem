"""
OpenAPI schema hooks for drf-spectacular.
Sets SERVERS from the request origin so Swagger UI "Try it out" uses the same origin (avoids Failed to fetch / CORS).
"""


def inject_servers_from_request(result, generator, request, public):
    """Set OpenAPI servers to the request origin so Swagger UI sends requests to the same host."""
    if request is None:
        return result
    try:
        base = request.build_absolute_uri("/").rstrip("/")
        if base and (base.startswith("http://") or base.startswith("https://")):
            result["servers"] = [{"url": base, "description": "This server (same origin)"}]
    except Exception:
        pass
    return result
