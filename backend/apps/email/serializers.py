from __future__ import annotations

from rest_framework import serializers

from apps.email.models import (
    Autoresponder,
    Mailbox,
    MailDomain,
    MailFilter,
    MailForwarder,
    MailingList,
)


class MailDomainSerializer(serializers.ModelSerializer):
    owner_username = serializers.CharField(source="owner.username", read_only=True)
    mailbox_count = serializers.SerializerMethodField()

    class Meta:
        model = MailDomain
        fields = (
            "id",
            "owner",
            "owner_username",
            "name",
            "domain",
            "is_active",
            "catch_all",
            "max_quota_mb",
            "dkim_enabled",
            "dkim_selector",
            "dkim_public_key",
            "spf_record",
            "dmarc_policy",
            "dmarc_rua",
            "mailbox_count",
            "created_at",
            "updated_at",
        )
        read_only_fields = (
            "id",
            "owner",
            "owner_username",
            "dkim_public_key",
            "mailbox_count",
            "created_at",
            "updated_at",
        )

    def get_mailbox_count(self, obj: MailDomain) -> int:
        return obj.mailboxes.count()


class MailDomainCreateSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=255)
    owner_id = serializers.IntegerField(required=False)
    domain_id = serializers.IntegerField(required=False, allow_null=True)
    max_quota_mb = serializers.IntegerField(required=False, min_value=1, default=1024)
    enable_dns = serializers.BooleanField(required=False, default=True)


class MailboxSerializer(serializers.ModelSerializer):
    address = serializers.CharField(read_only=True)
    status = serializers.CharField(read_only=True)
    domain_name = serializers.CharField(source="mail_domain.name", read_only=True)

    class Meta:
        model = Mailbox
        fields = (
            "id",
            "mail_domain",
            "domain_name",
            "local_part",
            "address",
            "quota_mb",
            "used_mb",
            "is_active",
            "is_suspended",
            "status",
            "maildir",
            "notes",
            "last_login_at",
            "created_at",
            "updated_at",
        )
        read_only_fields = (
            "id",
            "mail_domain",
            "domain_name",
            "local_part",
            "address",
            "used_mb",
            "status",
            "maildir",
            "last_login_at",
            "created_at",
            "updated_at",
        )


class MailboxCreateSerializer(serializers.Serializer):
    mail_domain_id = serializers.IntegerField()
    local_part = serializers.CharField(max_length=64)
    password = serializers.CharField(min_length=8, write_only=True)
    quota_mb = serializers.IntegerField(required=False, min_value=1)
    notes = serializers.CharField(required=False, allow_blank=True, default="")


class MailboxUpdateSerializer(serializers.Serializer):
    password = serializers.CharField(min_length=8, required=False, write_only=True)
    quota_mb = serializers.IntegerField(required=False, min_value=1)
    is_active = serializers.BooleanField(required=False)
    notes = serializers.CharField(required=False, allow_blank=True)


class MailForwarderSerializer(serializers.ModelSerializer):
    address = serializers.CharField(read_only=True)

    class Meta:
        model = MailForwarder
        fields = (
            "id",
            "mail_domain",
            "local_part",
            "address",
            "destinations",
            "keep_copy",
            "is_active",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("id", "mail_domain", "address", "created_at", "updated_at")


class MailForwarderCreateSerializer(serializers.Serializer):
    mail_domain_id = serializers.IntegerField()
    local_part = serializers.CharField(max_length=64)
    destinations = serializers.ListField(child=serializers.EmailField(), allow_empty=False)
    keep_copy = serializers.BooleanField(required=False, default=False)


class AutoresponderSerializer(serializers.ModelSerializer):
    is_currently_active = serializers.BooleanField(read_only=True)

    class Meta:
        model = Autoresponder
        fields = (
            "id",
            "mailbox",
            "is_active",
            "is_currently_active",
            "subject",
            "body",
            "start_at",
            "end_at",
            "interval_hours",
            "updated_at",
        )
        read_only_fields = ("id", "mailbox", "is_currently_active", "updated_at")


class AutoresponderUpdateSerializer(serializers.Serializer):
    is_active = serializers.BooleanField()
    subject = serializers.CharField(max_length=255)
    body = serializers.CharField(allow_blank=True)
    start_at = serializers.DateTimeField(required=False, allow_null=True)
    end_at = serializers.DateTimeField(required=False, allow_null=True)
    interval_hours = serializers.IntegerField(required=False, min_value=1, default=24)


class MailFilterSerializer(serializers.ModelSerializer):
    class Meta:
        model = MailFilter
        fields = (
            "id",
            "mailbox",
            "name",
            "match_field",
            "match_op",
            "match_value",
            "action",
            "action_value",
            "is_active",
            "priority",
            "created_at",
        )
        read_only_fields = ("id", "mailbox", "created_at")


class MailFilterCreateSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=120)
    match_field = serializers.ChoiceField(choices=["subject", "from", "to", "body"])
    match_op = serializers.ChoiceField(choices=["contains", "equals", "startswith"])
    match_value = serializers.CharField(max_length=255)
    action = serializers.ChoiceField(choices=["discard", "deliver", "forward", "stop"])
    action_value = serializers.CharField(required=False, allow_blank=True, default="")
    priority = serializers.IntegerField(required=False, default=100)


class MailingListSerializer(serializers.ModelSerializer):
    address = serializers.CharField(read_only=True)

    class Meta:
        model = MailingList
        fields = (
            "id",
            "mail_domain",
            "local_part",
            "address",
            "members",
            "is_active",
            "created_at",
        )
        read_only_fields = ("id", "mail_domain", "address", "created_at")


class MailingListCreateSerializer(serializers.Serializer):
    mail_domain_id = serializers.IntegerField()
    local_part = serializers.CharField(max_length=64)
    members = serializers.ListField(child=serializers.EmailField(), allow_empty=True, default=list)


class DkimEnableSerializer(serializers.Serializer):
    selector = serializers.CharField(required=False, default="default", max_length=63)


class DmarcUpdateSerializer(serializers.Serializer):
    dmarc_policy = serializers.ChoiceField(choices=["none", "quarantine", "reject"])
    dmarc_rua = serializers.EmailField(required=False, allow_blank=True, default="")
