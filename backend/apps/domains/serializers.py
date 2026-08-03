from __future__ import annotations

from rest_framework import serializers

from apps.domains.models import Domain, DomainRedirect, SslCertificate


class SslCertificateSerializer(serializers.ModelSerializer):
    is_expiring_soon = serializers.BooleanField(read_only=True)
    # Ne jamais exposer la clé privée en lecture liste/détail standard
    has_private_key = serializers.SerializerMethodField()

    class Meta:
        model = SslCertificate
        fields = (
            "id",
            "domain",
            "provider",
            "status",
            "common_name",
            "alt_names",
            "auto_renew",
            "issued_at",
            "expires_at",
            "last_error",
            "last_checked_at",
            "is_expiring_soon",
            "has_private_key",
            "created_at",
            "updated_at",
        )
        read_only_fields = fields

    def get_has_private_key(self, obj: SslCertificate) -> bool:
        return bool(obj.private_key_pem)


class DomainRedirectSerializer(serializers.ModelSerializer):
    class Meta:
        model = DomainRedirect
        fields = (
            "id",
            "domain",
            "source_path",
            "destination_url",
            "redirect_type",
            "wildcard",
            "is_active",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("id", "domain", "created_at", "updated_at")


class DomainSerializer(serializers.ModelSerializer):
    owner_username = serializers.CharField(source="owner.username", read_only=True)
    parent_name = serializers.CharField(source="parent.name", read_only=True, default=None)
    ssl = serializers.SerializerMethodField()
    redirects = DomainRedirectSerializer(many=True, read_only=True)
    dns_zone_name = serializers.CharField(source="dns_zone.name", read_only=True, default=None)

    class Meta:
        model = Domain
        fields = (
            "id",
            "name",
            "owner",
            "owner_username",
            "domain_type",
            "parent",
            "parent_name",
            "document_root",
            "is_active",
            "is_suspended",
            "create_dns_zone",
            "dns_zone",
            "dns_zone_name",
            "ipv4_address",
            "ipv6_address",
            "notes",
            "ssl",
            "redirects",
            "created_at",
            "updated_at",
        )
        read_only_fields = (
            "id",
            "owner",
            "owner_username",
            "parent_name",
            "dns_zone",
            "dns_zone_name",
            "ssl",
            "redirects",
            "created_at",
            "updated_at",
        )

    def get_ssl(self, obj: Domain):
        try:
            return SslCertificateSerializer(obj.ssl).data
        except SslCertificate.DoesNotExist:
            return None


class DomainCreateSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=255)
    domain_type = serializers.ChoiceField(
        choices=Domain.DomainType.choices,
        default=Domain.DomainType.PRIMARY,
    )
    owner_id = serializers.IntegerField(required=False)
    parent_id = serializers.IntegerField(required=False, allow_null=True)
    ipv4_address = serializers.IPAddressField(protocol="IPv4", required=False, allow_null=True)
    ipv6_address = serializers.IPAddressField(protocol="IPv6", required=False, allow_null=True)
    create_dns_zone = serializers.BooleanField(default=True)
    document_root = serializers.CharField(required=False, allow_blank=True, default="")
    notes = serializers.CharField(required=False, allow_blank=True, default="")


class SubdomainCreateSerializer(serializers.Serializer):
    label = serializers.RegexField(
        regex=r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$",
        max_length=63,
    )
    parent_id = serializers.IntegerField()
    ipv4_address = serializers.IPAddressField(protocol="IPv4", required=False, allow_null=True)


class RedirectCreateSerializer(serializers.Serializer):
    source_path = serializers.CharField(max_length=512, default="/")
    destination_url = serializers.URLField()
    redirect_type = serializers.ChoiceField(
        choices=DomainRedirect.RedirectType.choices,
        default=DomainRedirect.RedirectType.PERMANENT,
    )
    wildcard = serializers.BooleanField(default=False)


class LetsEncryptSerializer(serializers.Serializer):
    email = serializers.EmailField(required=False)


class CustomSslSerializer(serializers.Serializer):
    certificate_pem = serializers.CharField()
    private_key_pem = serializers.CharField()
    chain_pem = serializers.CharField(required=False, allow_blank=True, default="")
    auto_renew = serializers.BooleanField(default=False)
