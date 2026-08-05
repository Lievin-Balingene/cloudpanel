from __future__ import annotations

from rest_framework import serializers


class PathSerializer(serializers.Serializer):
    path = serializers.CharField(required=False, allow_blank=True, default="")


class MkdirSerializer(serializers.Serializer):
    path = serializers.CharField(required=False, allow_blank=True, default="")
    name = serializers.CharField(max_length=1024)
    recursive = serializers.BooleanField(required=False, default=False)


class CreateFileSerializer(serializers.Serializer):
    path = serializers.CharField(required=False, allow_blank=True, default="")
    name = serializers.CharField(max_length=255)
    content = serializers.CharField(required=False, allow_blank=True, default="")


class WriteFileSerializer(serializers.Serializer):
    path = serializers.CharField()
    content = serializers.CharField(allow_blank=True)


class PathsSerializer(serializers.Serializer):
    paths = serializers.ListField(child=serializers.CharField(), allow_empty=False)


class RenameSerializer(serializers.Serializer):
    path = serializers.CharField()
    new_name = serializers.CharField(max_length=255)


class TransferSerializer(serializers.Serializer):
    paths = serializers.ListField(child=serializers.CharField(), allow_empty=False)
    destination = serializers.CharField(required=False, allow_blank=True, default="")


class ChmodSerializer(serializers.Serializer):
    path = serializers.CharField()
    mode = serializers.RegexField(regex=r"^[0-7]{3,4}$")


class CompressSerializer(serializers.Serializer):
    paths = serializers.ListField(child=serializers.CharField(), allow_empty=False)
    archive = serializers.CharField()
    format = serializers.ChoiceField(choices=["zip", "tar.gz"], default="zip")


class DecompressSerializer(serializers.Serializer):
    archive = serializers.CharField()
    destination = serializers.CharField(required=False, allow_blank=True, allow_null=True)


class SearchSerializer(serializers.Serializer):
    query = serializers.CharField()
    path = serializers.CharField(required=False, allow_blank=True, default="")
    limit = serializers.IntegerField(required=False, min_value=1, max_value=500, default=200)


class UploadInitSerializer(serializers.Serializer):
    path = serializers.CharField(required=False, allow_blank=True, default="")
    name = serializers.CharField(max_length=1024)
    size = serializers.IntegerField(min_value=0)
    chunk_size = serializers.IntegerField(required=False, min_value=1024, max_value=16 * 1024 * 1024)


class UploadCompleteSerializer(serializers.Serializer):
    upload_id = serializers.CharField(max_length=64)


class UploadAbortSerializer(serializers.Serializer):
    upload_id = serializers.CharField(max_length=64)
