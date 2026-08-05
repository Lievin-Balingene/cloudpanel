"""API Transfer Tool (WHM)."""
from __future__ import annotations

import secrets
from pathlib import Path

from rest_framework import status
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.permissions import IsAdministrator
from apps.transfer.models import TransferJob
from apps.transfer.serializers import (
    ArchiveTransferSerializer,
    RemoteConnectSerializer,
    RemoteTransferSerializer,
    TransferJobSerializer,
)
from apps.transfer import services


def _job_payload(job: TransferJob) -> dict:
    data = TransferJobSerializer(
        {
            "id": job.id,
            "source_type": job.source_type,
            "status": job.status,
            "username": job.username,
            "email": job.email,
            "package_name": job.package_name,
            "overwrite": job.overwrite,
            "archive_name": job.archive_name,
            "remote_host": job.remote_host,
            "remote_username": job.remote_username,
            "progress": job.progress,
            "current_step": job.current_step,
            "log": job.log,
            "result": job.result,
            "last_error": job.last_error,
            "started_at": job.started_at,
            "finished_at": job.finished_at,
            "created_at": job.created_at,
        }
    ).data
    # Masquer mot de passe après première lecture côté client si job ancien
    if job.status != TransferJob.Status.COMPLETED:
        if isinstance(data.get("result"), dict):
            data["result"] = {**data["result"], "password": ""}
    return data


class TransferJobListView(APIView):
    permission_classes = [IsAuthenticated, IsAdministrator]

    def get(self, request: Request) -> Response:
        jobs = TransferJob.objects.all()[:50]
        return Response({"success": True, "data": [_job_payload(j) for j in jobs]})


class TransferJobDetailView(APIView):
    permission_classes = [IsAuthenticated, IsAdministrator]

    def get(self, request: Request, pk: int) -> Response:
        job = TransferJob.objects.filter(pk=pk).first()
        if job is None:
            return Response(
                {"success": False, "error": {"code": "not_found", "message": "Job introuvable."}},
                status=status.HTTP_404_NOT_FOUND,
            )
        return Response({"success": True, "data": _job_payload(job)})


class TransferArchiveInspectView(APIView):
    permission_classes = [IsAuthenticated, IsAdministrator]
    parser_classes = [MultiPartParser, FormParser]

    def post(self, request: Request) -> Response:
        upload = request.FILES.get("file")
        if upload is None:
            return Response(
                {"success": False, "error": {"code": "missing_file", "message": "Archive requise."}},
                status=status.HTTP_400_BAD_REQUEST,
            )
        dest = services.transfer_root() / "uploads" / f"inspect-{secrets.token_hex(8)}-{Path(upload.name).name}"
        with dest.open("wb") as out:
            for chunk in upload.chunks():
                out.write(chunk)
        try:
            data = services.inspect_uploaded_archive(dest)
            data["archive_name"] = Path(upload.name).name
            data["temp_path"] = str(dest)
            return Response({"success": True, "data": data})
        finally:
            # garder le fichier pour un éventuel start immédiat via path renvoyé
            pass


class TransferArchiveStartView(APIView):
    permission_classes = [IsAuthenticated, IsAdministrator]
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def post(self, request: Request) -> Response:
        upload = request.FILES.get("file")
        # Champs form + JSON
        raw = {
            "username": request.data.get("username", ""),
            "email": request.data.get("email", ""),
            "password": request.data.get("password", ""),
            "package_name": request.data.get("package_name", ""),
            "overwrite": str(request.data.get("overwrite", "false")).lower() in {"1", "true", "yes", "on"},
        }
        options_raw = request.data.get("options")
        if isinstance(options_raw, str):
            import json

            try:
                options_raw = json.loads(options_raw)
            except json.JSONDecodeError:
                options_raw = None
        if isinstance(options_raw, dict):
            raw["options"] = options_raw

        serializer = ArchiveTransferSerializer(data=raw)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        temp_path = request.data.get("temp_path") or ""
        if upload is not None:
            dest = (
                services.transfer_root()
                / "uploads"
                / f"job-{secrets.token_hex(8)}-{Path(upload.name).name}"
            )
            with dest.open("wb") as out:
                for chunk in upload.chunks():
                    out.write(chunk)
            archive_name = Path(upload.name).name
            archive_path = dest
        elif temp_path:
            archive_path = Path(str(temp_path))
            if not archive_path.is_file():
                return Response(
                    {
                        "success": False,
                        "error": {"code": "missing_file", "message": "temp_path invalide."},
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )
            archive_name = archive_path.name
        else:
            return Response(
                {"success": False, "error": {"code": "missing_file", "message": "Archive requise."}},
                status=status.HTTP_400_BAD_REQUEST,
            )

        job = services.create_archive_job(
            actor=request.user,
            archive_path=archive_path,
            archive_name=archive_name,
            username=data["username"],
            email=data.get("email") or "",
            password=data.get("password") or "",
            package_name=data.get("package_name") or "",
            overwrite=bool(data.get("overwrite")),
            options=data.get("options"),
        )
        return Response({"success": True, "data": _job_payload(job)}, status=status.HTTP_201_CREATED)


class TransferRemoteListView(APIView):
    permission_classes = [IsAuthenticated, IsAdministrator]

    def post(self, request: Request) -> Response:
        serializer = RemoteConnectSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        result = services.remote_list_accounts(
            host=data["host"],
            port=data.get("port") or 2087,
            user=data.get("user") or "root",
            token=data["token"],
            insecure_ssl=bool(data.get("insecure_ssl")),
            ssh_port=data.get("ssh_port") or 22,
        )
        return Response({"success": True, "data": result})


class TransferRemoteStartView(APIView):
    permission_classes = [IsAuthenticated, IsAdministrator]

    def post(self, request: Request) -> Response:
        serializer = RemoteTransferSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        job = services.create_remote_job(
            actor=request.user,
            host=data["host"],
            port=data.get("port") or 2087,
            whm_user=data.get("user") or "root",
            token=data["token"],
            remote_username=data["remote_username"],
            email=data.get("email") or "",
            password=data.get("password") or "",
            package_name=data.get("package_name") or "",
            overwrite=bool(data.get("overwrite")),
            insecure_ssl=bool(data.get("insecure_ssl")),
            ssh_port=data.get("ssh_port") or 22,
            options=data.get("options"),
        )
        return Response({"success": True, "data": _job_payload(job)}, status=status.HTTP_201_CREATED)
