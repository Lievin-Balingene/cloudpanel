"""API domaines et SSL."""
from __future__ import annotations

from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.models import User
from apps.domains.models import Domain, DomainRedirect
from apps.domains.serializers import (
    CustomSslSerializer,
    DomainCreateSerializer,
    DomainRedirectSerializer,
    DomainSerializer,
    LetsEncryptSerializer,
    RedirectCreateSerializer,
    SslCertificateSerializer,
    SubdomainCreateSerializer,
)
from apps.domains.services import (
    create_domain,
    create_redirect,
    delete_domain,
    domains_queryset_for,
)
from apps.domains.ssl_services import install_custom_certificate, issue_letsencrypt


class DomainListCreateView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request) -> Response:
        qs = domains_queryset_for(request.user)
        dtype = request.query_params.get("type")
        if dtype:
            qs = qs.filter(domain_type=dtype)
        return Response({"success": True, "data": DomainSerializer(qs, many=True).data})

    def post(self, request: Request) -> Response:
        serializer = DomainCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        owner = request.user
        if data.get("owner_id") and request.user.role in {
            User.Role.ADMINISTRATOR,
            User.Role.RESELLER,
        }:
            owner = get_object_or_404(User, pk=data["owner_id"])
            if request.user.role == User.Role.RESELLER and owner.parent_id != request.user.pk:
                return Response(status=status.HTTP_403_FORBIDDEN)

        parent = None
        if data.get("parent_id"):
            parent = get_object_or_404(domains_queryset_for(request.user), pk=data["parent_id"])

        create_dns = data.get("create_dns_zone")
        if create_dns is None:
            try:
                from apps.server_setup.tweak_settings import get_tweak

                create_dns = bool(get_tweak("auto_create_dns_zone", True))
            except Exception:  # noqa: BLE001
                create_dns = True

        domain = create_domain(
            name=data["name"],
            owner=owner,
            domain_type=data["domain_type"],
            parent=parent,
            ipv4_address=data.get("ipv4_address"),
            ipv6_address=data.get("ipv6_address"),
            create_dns_zone=bool(create_dns),
            document_root=data.get("document_root") or "",
            notes=data.get("notes") or "",
            web_engine=data.get("web_engine"),
        )
        return Response(
            {"success": True, "data": DomainSerializer(domain).data},
            status=status.HTTP_201_CREATED,
        )


class DomainDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request, pk: int) -> Response:
        domain = get_object_or_404(domains_queryset_for(request.user), pk=pk)
        return Response({"success": True, "data": DomainSerializer(domain).data})

    def patch(self, request: Request, pk: int) -> Response:
        domain = get_object_or_404(domains_queryset_for(request.user), pk=pk)
        serializer = DomainSerializer(domain, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        if "web_engine" in data and data["web_engine"] == Domain.WebEngine.OLS:
            from apps.domains.ols_vhosts import ols_enabled, ols_installed

            if not ols_enabled() or not ols_installed():
                return Response(
                    {
                        "success": False,
                        "error": {
                            "code": "ols_unavailable",
                            "message": (
                                "OpenLiteSpeed non disponible. "
                                "VZONE_OLS_ENABLED=1 + install-openlitespeed.sh"
                            ),
                        },
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )
        serializer.save()
        domain.refresh_from_db()
        # Sync PHP handler hint + vhosts
        if domain.web_engine == Domain.WebEngine.OLS:
            try:
                from apps.php.models import PhpSelector

                PhpSelector.objects.filter(
                    domain_name__iexact=domain.name, is_active=True
                ).update(handler=PhpSelector.Handler.LSAPI)
            except Exception:  # noqa: BLE001
                pass
        try:
            from apps.domains.vhosts import sync_domain_vhost

            sync_domain_vhost(domain)
        except Exception:  # noqa: BLE001
            pass
        return Response({"success": True, "data": DomainSerializer(domain).data})

    def delete(self, request: Request, pk: int) -> Response:
        domain = get_object_or_404(domains_queryset_for(request.user), pk=pk)
        remove_dns = str(request.query_params.get("remove_dns", "false")).lower() in {
            "1",
            "true",
            "yes",
        }
        delete_domain(domain, remove_dns_zone=remove_dns)
        return Response(status=status.HTTP_204_NO_CONTENT)


class SubdomainCreateView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request: Request) -> Response:
        serializer = SubdomainCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        parent = get_object_or_404(
            domains_queryset_for(request.user),
            pk=serializer.validated_data["parent_id"],
        )
        hostname = f"{serializer.validated_data['label']}.{parent.name}"
        domain = create_domain(
            name=hostname,
            owner=parent.owner,
            domain_type=Domain.DomainType.SUBDOMAIN,
            parent=parent,
            ipv4_address=serializer.validated_data.get("ipv4_address") or parent.ipv4_address,
            create_dns_zone=False,
            web_engine=parent.web_engine or None,
        )
        return Response(
            {"success": True, "data": DomainSerializer(domain).data},
            status=status.HTTP_201_CREATED,
        )


class DomainRedirectListCreateView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request, domain_id: int) -> Response:
        domain = get_object_or_404(domains_queryset_for(request.user), pk=domain_id)
        return Response(
            {
                "success": True,
                "data": DomainRedirectSerializer(domain.redirects.all(), many=True).data,
            }
        )

    def post(self, request: Request, domain_id: int) -> Response:
        domain = get_object_or_404(domains_queryset_for(request.user), pk=domain_id)
        serializer = RedirectCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        redirect = create_redirect(domain=domain, **serializer.validated_data)
        return Response(
            {"success": True, "data": DomainRedirectSerializer(redirect).data},
            status=status.HTTP_201_CREATED,
        )


class DomainRedirectDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def delete(self, request: Request, domain_id: int, pk: int) -> Response:
        domain = get_object_or_404(domains_queryset_for(request.user), pk=domain_id)
        redirect = get_object_or_404(DomainRedirect, pk=pk, domain=domain)
        redirect.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class SslIssueLetsEncryptView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request: Request, domain_id: int) -> Response:
        domain = get_object_or_404(domains_queryset_for(request.user), pk=domain_id)
        serializer = LetsEncryptSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        ssl = issue_letsencrypt(
            domain,
            email=serializer.validated_data.get("email"),
        )
        return Response({"success": True, "data": SslCertificateSerializer(ssl).data})


class SslInstallCustomView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request: Request, domain_id: int) -> Response:
        domain = get_object_or_404(domains_queryset_for(request.user), pk=domain_id)
        serializer = CustomSslSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        ssl = install_custom_certificate(domain, **serializer.validated_data)
        return Response({"success": True, "data": SslCertificateSerializer(ssl).data})


class SslStatusView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request, domain_id: int) -> Response:
        domain = get_object_or_404(domains_queryset_for(request.user), pk=domain_id)
        if not hasattr(domain, "ssl"):
            return Response({"success": True, "data": None})
        return Response({"success": True, "data": SslCertificateSerializer(domain.ssl).data})


def _assert_can_read_domain_logs(actor, owner) -> None:  # type: ignore[no-untyped-def]
    """Client = ses logs ; WHM admin OK ; reseller = list-accts + parent."""
    from apps.accounts.models import User
    from apps.core.exceptions import VZoneAPIException

    if actor.pk == owner.pk:
        return
    if getattr(actor, "role", None) == User.Role.ADMINISTRATOR:
        return
    if getattr(actor, "role", None) == User.Role.RESELLER:
        if owner.parent_id != actor.id:
            raise VZoneAPIException(
                detail="Domaine hors de votre périmètre reseller.",
                code="forbidden",
                status_code=403,
            )
        if not actor.has_reseller_priv("list-accts"):
            raise VZoneAPIException(
                detail="Privilege list-accts requis pour les journaux.",
                code="reseller_privilege_denied",
                status_code=403,
            )
        return
    raise VZoneAPIException(
        detail="Accès journaux refusé.",
        code="forbidden",
        status_code=403,
    )


class DomainLogsListView(APIView):
    """Index des journaux d'un domaine (client + WHM)."""

    permission_classes = [IsAuthenticated]

    def get(self, request: Request, domain_id: int) -> Response:
        from apps.accounts.account_logs import list_account_logs, sanitize_logs_for_actor

        domain = get_object_or_404(domains_queryset_for(request.user), pk=domain_id)
        _assert_can_read_domain_logs(request.user, domain.owner)
        data = list_account_logs(domain.owner)
        # Restreindre à ce domaine
        data["domains"] = [d for d in data["domains"] if d["id"] == domain.id]
        data["total_available"] = sum(d["available_count"] for d in data["domains"])
        data["focus_domain"] = domain.name
        return Response({"success": True, "data": sanitize_logs_for_actor(data, request.user)})


class DomainLogsTailView(APIView):
    """Tail journal pour un domaine accessible à l'utilisateur."""

    permission_classes = [IsAuthenticated]

    def get(self, request: Request, domain_id: int) -> Response:
        from apps.accounts.account_logs import sanitize_log_tail_for_actor, tail_account_log

        domain = get_object_or_404(domains_queryset_for(request.user), pk=domain_id)
        _assert_can_read_domain_logs(request.user, domain.owner)
        kind = (request.query_params.get("kind") or "access").strip()
        try:
            lines = int(request.query_params.get("lines") or 200)
        except (TypeError, ValueError):
            lines = 200
        data = tail_account_log(
            domain.owner,
            domain_name=domain.name,
            kind=kind,
            lines=lines,
        )
        return Response({"success": True, "data": sanitize_log_tail_for_actor(data, request.user)})
