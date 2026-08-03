"""API File Manager."""
from __future__ import annotations

from dataclasses import asdict

from django.http import FileResponse
from rest_framework import status
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.files import services
from apps.files.serializers import (
    ChmodSerializer,
    CompressSerializer,
    CreateFileSerializer,
    DecompressSerializer,
    MkdirSerializer,
    PathSerializer,
    PathsSerializer,
    RenameSerializer,
    SearchSerializer,
    TransferSerializer,
    WriteFileSerializer,
)


class FileListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request) -> Response:
        path = request.query_params.get("path", "")
        data = services.list_directory(request.user, path)
        return Response({"success": True, "data": data})


class FileMkdirView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request: Request) -> Response:
        serializer = MkdirSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        entry = services.mkdir(
            request.user,
            serializer.validated_data["path"],
            serializer.validated_data["name"],
        )
        return Response({"success": True, "data": asdict(entry)}, status=status.HTTP_201_CREATED)


class FileCreateView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request: Request) -> Response:
        serializer = CreateFileSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        entry = services.create_file(
            request.user,
            serializer.validated_data["path"],
            serializer.validated_data["name"],
            serializer.validated_data.get("content", ""),
        )
        return Response({"success": True, "data": asdict(entry)}, status=status.HTTP_201_CREATED)


class FileReadView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request) -> Response:
        serializer = PathSerializer(data=request.query_params)
        serializer.is_valid(raise_exception=True)
        data = services.read_file(request.user, serializer.validated_data.get("path") or "")
        return Response({"success": True, "data": data})


class FileWriteView(APIView):
    permission_classes = [IsAuthenticated]

    def put(self, request: Request) -> Response:
        serializer = WriteFileSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        entry = services.write_file(
            request.user,
            serializer.validated_data["path"],
            serializer.validated_data["content"],
        )
        return Response({"success": True, "data": asdict(entry)})


class FileDeleteView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request: Request) -> Response:
        serializer = PathsSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        count = services.delete_paths(request.user, serializer.validated_data["paths"])
        return Response({"success": True, "data": {"deleted": count}})


class FileRenameView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request: Request) -> Response:
        serializer = RenameSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        entry = services.rename_path(
            request.user,
            serializer.validated_data["path"],
            serializer.validated_data["new_name"],
        )
        return Response({"success": True, "data": asdict(entry)})


class FileCopyView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request: Request) -> Response:
        serializer = TransferSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        entries = services.copy_paths(
            request.user,
            serializer.validated_data["paths"],
            serializer.validated_data.get("destination") or "",
        )
        return Response({"success": True, "data": [asdict(e) for e in entries]})


class FileMoveView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request: Request) -> Response:
        serializer = TransferSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        entries = services.move_paths(
            request.user,
            serializer.validated_data["paths"],
            serializer.validated_data.get("destination") or "",
        )
        return Response({"success": True, "data": [asdict(e) for e in entries]})


class FileChmodView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request: Request) -> Response:
        serializer = ChmodSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        entry = services.chmod_path(
            request.user,
            serializer.validated_data["path"],
            serializer.validated_data["mode"],
        )
        return Response({"success": True, "data": asdict(entry)})


class FileCompressView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request: Request) -> Response:
        serializer = CompressSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        entry = services.compress(
            request.user,
            serializer.validated_data["paths"],
            serializer.validated_data["archive"],
            serializer.validated_data["format"],
        )
        return Response({"success": True, "data": asdict(entry)}, status=status.HTTP_201_CREATED)


class FileDecompressView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request: Request) -> Response:
        serializer = DecompressSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = services.decompress(
            request.user,
            serializer.validated_data["archive"],
            serializer.validated_data.get("destination"),
        )
        return Response({"success": True, "data": data})


class FileSearchView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request) -> Response:
        serializer = SearchSerializer(data=request.query_params)
        serializer.is_valid(raise_exception=True)
        results = services.search_files(
            request.user,
            serializer.validated_data["query"],
            serializer.validated_data.get("path") or "",
            serializer.validated_data.get("limit", 200),
        )
        return Response({"success": True, "data": results})


class FileUploadView(APIView):
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]

    def post(self, request: Request) -> Response:
        upload = request.FILES.get("file")
        if upload is None:
            return Response(
                {
                    "success": False,
                    "error": {"code": "missing_file", "message": "Fichier requis (champ file)."},
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        path = request.data.get("path", "")
        entry = services.save_upload(
            request.user,
            path,
            upload.name,
            upload.file,
            getattr(upload, "size", None),
        )
        return Response({"success": True, "data": asdict(entry)}, status=status.HTTP_201_CREATED)


class FileDownloadView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request) -> Response:
        rel = request.query_params.get("path", "")
        path = services.resolve_path(request.user, rel)
        if not path.is_file():
            return Response(
                {
                    "success": False,
                    "error": {"code": "not_found", "message": "Fichier introuvable."},
                },
                status=status.HTTP_404_NOT_FOUND,
            )
        return FileResponse(path.open("rb"), as_attachment=True, filename=path.name)


class FilePreviewView(APIView):
    permission_classes = [IsAuthenticated]
    parser_classes = [JSONParser]

    def get(self, request: Request) -> Response:
        rel = request.query_params.get("path", "")
        path = services.resolve_path(request.user, rel)
        if not path.exists():
            return Response(
                {
                    "success": False,
                    "error": {"code": "not_found", "message": "Introuvable."},
                },
                status=status.HTTP_404_NOT_FOUND,
            )
        entry = services.entry_from_path(request.user, path)
        preview: dict = {"entry": asdict(entry)}
        if path.is_file() and entry.is_text and entry.size <= services.MAX_EDITOR_BYTES:
            preview["content"] = services.read_file(request.user, rel)["content"][:4000]
        elif path.is_file() and entry.mime and entry.mime.startswith("image/"):
            preview["image"] = True
        return Response({"success": True, "data": preview})
