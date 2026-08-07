"""Configuration ASGI avec HTTP + WebSockets Channels."""
from __future__ import annotations

import os

from channels.auth import AuthMiddlewareStack
from channels.routing import ProtocolTypeRouter, URLRouter
from django.core.asgi import get_asgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "vzone.settings.development")

django_asgi_app = get_asgi_application()

from vzone.routing import websocket_urlpatterns  # noqa: E402

# Pas d'AllowedHostsOriginValidator : accès style cPanel via domaine:9082/9086
# (Origin = domaine client ∉ ALLOWED_HOSTS). Le terminal est protégé par JWT.
application = ProtocolTypeRouter(
    {
        "http": django_asgi_app,
        "websocket": AuthMiddlewareStack(URLRouter(websocket_urlpatterns)),
    }
)
