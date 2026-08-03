"""API e-mail."""
from __future__ import annotations

from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.models import User
from apps.email.models import Mailbox, MailDomain, MailFilter, MailForwarder, MailingList
from apps.email.serializers import (
    AutoresponderSerializer,
    AutoresponderUpdateSerializer,
    DkimEnableSerializer,
    DmarcUpdateSerializer,
    MailboxCreateSerializer,
    MailboxSerializer,
    MailboxUpdateSerializer,
    MailDomainCreateSerializer,
    MailDomainSerializer,
    MailFilterCreateSerializer,
    MailFilterSerializer,
    MailForwarderCreateSerializer,
    MailForwarderSerializer,
    MailingListCreateSerializer,
    MailingListSerializer,
)
from apps.email.services import (
    create_filter,
    create_forwarder,
    create_mail_domain,
    create_mailbox,
    create_mailing_list,
    create_webmail_sso,
    delete_mailbox,
    enable_dkim,
    mail_domains_qs,
    mailboxes_qs,
    set_autoresponder,
    suspend_mailbox,
    sync_mail_dns,
    update_mailbox,
    webmail_url,
    write_mail_maps,
)


class MailDomainListCreateView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request) -> Response:
        qs = mail_domains_qs(request.user)
        data = []
        for md in qs:
            item = MailDomainSerializer(md).data
            item["mailbox_count"] = md.mailboxes.count()
            data.append(item)
        return Response({"success": True, "data": data})

    def post(self, request: Request) -> Response:
        serializer = MailDomainCreateSerializer(data=request.data)
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
        md = create_mail_domain(
            owner=owner,
            name=data["name"],
            domain_id=data.get("domain_id"),
            max_quota_mb=data.get("max_quota_mb", 1024),
            enable_dns=data.get("enable_dns", True),
        )
        return Response(
            {"success": True, "data": MailDomainSerializer(md).data},
            status=status.HTTP_201_CREATED,
        )


class MailDomainDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request, pk: int) -> Response:
        md = get_object_or_404(mail_domains_qs(request.user), pk=pk)
        data = MailDomainSerializer(md).data
        data["mailbox_count"] = md.mailboxes.count()
        return Response({"success": True, "data": data})

    def delete(self, request: Request, pk: int) -> Response:
        md = get_object_or_404(mail_domains_qs(request.user), pk=pk)
        md.delete()
        write_mail_maps()
        return Response(status=status.HTTP_204_NO_CONTENT)


class MailDnsSyncView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request: Request, pk: int) -> Response:
        md = get_object_or_404(mail_domains_qs(request.user), pk=pk)
        records = sync_mail_dns(md)
        return Response({"success": True, "data": records})


class MailDkimEnableView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request: Request, pk: int) -> Response:
        md = get_object_or_404(mail_domains_qs(request.user), pk=pk)
        serializer = DkimEnableSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        md = enable_dkim(md, selector=serializer.validated_data.get("selector", "default"))
        return Response({"success": True, "data": MailDomainSerializer(md).data})


class MailDmarcUpdateView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request: Request, pk: int) -> Response:
        md = get_object_or_404(mail_domains_qs(request.user), pk=pk)
        serializer = DmarcUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        md.dmarc_policy = serializer.validated_data["dmarc_policy"]
        md.dmarc_rua = serializer.validated_data.get("dmarc_rua", "")
        md.save(update_fields=["dmarc_policy", "dmarc_rua", "updated_at"])
        sync_mail_dns(md)
        return Response({"success": True, "data": MailDomainSerializer(md).data})


class MailboxListCreateView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request) -> Response:
        qs = mailboxes_qs(request.user)
        domain_id = request.query_params.get("mail_domain_id")
        if domain_id:
            qs = qs.filter(mail_domain_id=domain_id)
        return Response({"success": True, "data": MailboxSerializer(qs, many=True).data})

    def post(self, request: Request) -> Response:
        serializer = MailboxCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        md = get_object_or_404(mail_domains_qs(request.user), pk=data["mail_domain_id"])
        box = create_mailbox(
            mail_domain=md,
            local_part=data["local_part"],
            password=data["password"],
            quota_mb=data.get("quota_mb"),
            notes=data.get("notes", ""),
        )
        return Response(
            {"success": True, "data": MailboxSerializer(box).data},
            status=status.HTTP_201_CREATED,
        )


class MailboxDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request, pk: int) -> Response:
        box = get_object_or_404(mailboxes_qs(request.user), pk=pk)
        return Response({"success": True, "data": MailboxSerializer(box).data})

    def patch(self, request: Request, pk: int) -> Response:
        box = get_object_or_404(mailboxes_qs(request.user), pk=pk)
        serializer = MailboxUpdateSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        box = update_mailbox(box, **serializer.validated_data)
        return Response({"success": True, "data": MailboxSerializer(box).data})

    def delete(self, request: Request, pk: int) -> Response:
        box = get_object_or_404(mailboxes_qs(request.user), pk=pk)
        delete_mailbox(box)
        return Response(status=status.HTTP_204_NO_CONTENT)


class MailboxSuspendView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request: Request, pk: int) -> Response:
        box = get_object_or_404(mailboxes_qs(request.user), pk=pk)
        suspended = bool(request.data.get("suspended", True))
        box = suspend_mailbox(box, suspended=suspended)
        return Response({"success": True, "data": MailboxSerializer(box).data})


class MailboxAutoresponderView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request, pk: int) -> Response:
        box = get_object_or_404(mailboxes_qs(request.user), pk=pk)
        ar = getattr(box, "autoresponder", None)
        if ar is None:
            return Response({"success": True, "data": None})
        return Response({"success": True, "data": AutoresponderSerializer(ar).data})

    def put(self, request: Request, pk: int) -> Response:
        box = get_object_or_404(mailboxes_qs(request.user), pk=pk)
        serializer = AutoresponderUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        ar = set_autoresponder(box, **serializer.validated_data)
        return Response({"success": True, "data": AutoresponderSerializer(ar).data})


class MailboxFilterListCreateView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request, pk: int) -> Response:
        box = get_object_or_404(mailboxes_qs(request.user), pk=pk)
        return Response(
            {"success": True, "data": MailFilterSerializer(box.filters.all(), many=True).data}
        )

    def post(self, request: Request, pk: int) -> Response:
        box = get_object_or_404(mailboxes_qs(request.user), pk=pk)
        serializer = MailFilterCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        filt = create_filter(box, **serializer.validated_data)
        return Response(
            {"success": True, "data": MailFilterSerializer(filt).data},
            status=status.HTTP_201_CREATED,
        )


class MailFilterDeleteView(APIView):
    permission_classes = [IsAuthenticated]

    def delete(self, request: Request, pk: int, filter_id: int) -> Response:
        box = get_object_or_404(mailboxes_qs(request.user), pk=pk)
        filt = get_object_or_404(MailFilter, pk=filter_id, mailbox=box)
        filt.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class ForwarderListCreateView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request) -> Response:
        domains = mail_domains_qs(request.user)
        qs = MailForwarder.objects.filter(mail_domain__in=domains).select_related("mail_domain")
        domain_id = request.query_params.get("mail_domain_id")
        if domain_id:
            qs = qs.filter(mail_domain_id=domain_id)
        return Response({"success": True, "data": MailForwarderSerializer(qs, many=True).data})

    def post(self, request: Request) -> Response:
        serializer = MailForwarderCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        md = get_object_or_404(mail_domains_qs(request.user), pk=data["mail_domain_id"])
        fwd = create_forwarder(
            mail_domain=md,
            local_part=data["local_part"],
            destinations=data["destinations"],
            keep_copy=data.get("keep_copy", False),
        )
        return Response(
            {"success": True, "data": MailForwarderSerializer(fwd).data},
            status=status.HTTP_201_CREATED,
        )


class ForwarderDeleteView(APIView):
    permission_classes = [IsAuthenticated]

    def delete(self, request: Request, pk: int) -> Response:
        domains = mail_domains_qs(request.user)
        fwd = get_object_or_404(MailForwarder, pk=pk, mail_domain__in=domains)
        fwd.delete()
        write_mail_maps()
        return Response(status=status.HTTP_204_NO_CONTENT)


class MailingListListCreateView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request) -> Response:
        domains = mail_domains_qs(request.user)
        qs = MailingList.objects.filter(mail_domain__in=domains)
        return Response({"success": True, "data": MailingListSerializer(qs, many=True).data})

    def post(self, request: Request) -> Response:
        serializer = MailingListCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        md = get_object_or_404(mail_domains_qs(request.user), pk=data["mail_domain_id"])
        lst = create_mailing_list(md, local_part=data["local_part"], members=data.get("members", []))
        return Response(
            {"success": True, "data": MailingListSerializer(lst).data},
            status=status.HTTP_201_CREATED,
        )


class EmailOverviewView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request) -> Response:
        domains = mail_domains_qs(request.user)
        boxes = mailboxes_qs(request.user)
        return Response(
            {
                "success": True,
                "data": {
                    "domains": domains.count(),
                    "mailboxes": boxes.count(),
                    "active_mailboxes": boxes.filter(is_active=True, is_suspended=False).count(),
                    "forwarders": MailForwarder.objects.filter(mail_domain__in=domains).count(),
                    "webmail_url": webmail_url(),
                },
            }
        )


class WebmailSsoView(APIView):
    """Ouvre Roundcube authentifié pour une boîte (SSO one-shot)."""

    permission_classes = [IsAuthenticated]

    def post(self, request: Request) -> Response:
        mailbox_id = request.data.get("mailbox_id")
        if not mailbox_id:
            return Response(
                {"success": False, "error": {"message": "mailbox_id requis.", "code": "validation"}},
                status=status.HTTP_400_BAD_REQUEST,
            )
        box = get_object_or_404(mailboxes_qs(request.user), pk=mailbox_id)
        data = create_webmail_sso(box)
        return Response({"success": True, "data": data})
