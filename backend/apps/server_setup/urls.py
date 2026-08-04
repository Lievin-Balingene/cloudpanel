from __future__ import annotations

from django.urls import path

from apps.server_setup.views import ServerSetupView

urlpatterns = [
    path("", ServerSetupView.as_view(), name="server-setup"),
]
