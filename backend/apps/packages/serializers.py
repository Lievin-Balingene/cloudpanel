"""Sérialiseurs packages."""
from __future__ import annotations

from rest_framework import serializers

from apps.packages.models import HostingPackage, PackageAssignment


class HostingPackageSerializer(serializers.ModelSerializer):
    assigned_count = serializers.IntegerField(read_only=True, required=False)

    class Meta:
        model = HostingPackage
        fields = (
            "id",
            "name",
            "slug",
            "description",
            "package_type",
            "is_active",
            "is_default",
            "disk_mb",
            "bandwidth_mb",
            "unlimited_disk",
            "unlimited_bandwidth",
            "cpu_millicores",
            "ram_mb",
            "unlimited_cpu",
            "unlimited_ram",
            "inode_limit",
            "max_processes",
            "max_nproc",
            "max_entry_processes",
            "domains",
            "subdomains",
            "parked_domains",
            "addon_domains",
            "emails",
            "email_lists",
            "databases",
            "ftp_accounts",
            "python_apps",
            "node_apps",
            "docker_containers",
            "cron_jobs",
            "max_accounts",
            "can_create_packages",
            "allow_ssh",
            "allow_dns",
            "allow_ssl",
            "allow_backup",
            "allow_git",
            "owner",
            "sort_order",
            "assigned_count",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("id", "slug", "owner", "created_at", "updated_at", "assigned_count")


class PackageAssignmentSerializer(serializers.ModelSerializer):
    package = HostingPackageSerializer(read_only=True)
    package_id = serializers.PrimaryKeyRelatedField(
        source="package",
        queryset=HostingPackage.objects.filter(is_active=True),
        write_only=True,
    )
    username = serializers.CharField(source="user.username", read_only=True)
    user_id = serializers.IntegerField(source="user.id", read_only=True)

    class Meta:
        model = PackageAssignment
        fields = (
            "id",
            "user_id",
            "username",
            "package",
            "package_id",
            "assigned_at",
            "notes",
        )
        read_only_fields = ("id", "user_id", "username", "package", "assigned_at")


class AssignPackageSerializer(serializers.Serializer):
    user_id = serializers.IntegerField()
    package_id = serializers.IntegerField()
    notes = serializers.CharField(required=False, allow_blank=True, default="")
