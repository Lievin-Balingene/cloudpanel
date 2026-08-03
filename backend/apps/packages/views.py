"""Vues API packages."""
from __future__ import annotations

from django.db.models import Count, Q
from rest_framework import generics, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.models import User
from apps.core.permissions import IsAdministrator, IsResellerOrAdmin
from apps.packages.models import HostingPackage, PackageAssignment
from apps.packages.serializers import (
    AssignPackageSerializer,
    HostingPackageSerializer,
    PackageAssignmentSerializer,
)
from apps.packages.services import apply_package_to_user, seed_default_packages


class PackageListCreateView(generics.ListCreateAPIView):
    permission_classes = [IsAuthenticated, IsResellerOrAdmin]
    serializer_class = HostingPackageSerializer

    def get_queryset(self):
        user = self.request.user
        qs = HostingPackage.objects.annotate(assigned_count=Count("assignments"))
        ptype = self.request.query_params.get("type")
        if ptype:
            qs = qs.filter(package_type=ptype)
        if user.role == User.Role.ADMINISTRATOR:
            return qs
        return qs.filter(Q(owner=user) | Q(owner__isnull=True, package_type=HostingPackage.PackageType.CLIENT))

    def list(self, request: Request, *args, **kwargs) -> Response:
        serializer = self.get_serializer(self.get_queryset(), many=True)
        return Response({"success": True, "data": serializer.data})

    def create(self, request: Request, *args, **kwargs) -> Response:
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        owner = None if request.user.role == User.Role.ADMINISTRATOR else request.user
        if request.user.role == User.Role.RESELLER:
            assignment = PackageAssignment.objects.filter(user=request.user).select_related("package").first()
            if not assignment or not assignment.package.can_create_packages:
                return Response(
                    {
                        "success": False,
                        "error": {
                            "code": "forbidden",
                            "message": "Ce revendeur ne peut pas créer de packages.",
                        },
                    },
                    status=status.HTTP_403_FORBIDDEN,
                )
            if serializer.validated_data.get("package_type") != HostingPackage.PackageType.CLIENT:
                return Response(
                    {
                        "success": False,
                        "error": {
                            "code": "invalid",
                            "message": "Un revendeur ne crée que des packages clients.",
                        },
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )
        pkg = serializer.save(owner=owner)
        return Response(
            {"success": True, "data": HostingPackageSerializer(pkg).data},
            status=status.HTTP_201_CREATED,
        )


class PackageDetailView(generics.RetrieveUpdateDestroyAPIView):
    permission_classes = [IsAuthenticated, IsResellerOrAdmin]
    serializer_class = HostingPackageSerializer

    def get_queryset(self):
        user = self.request.user
        qs = HostingPackage.objects.annotate(assigned_count=Count("assignments"))
        if user.role == User.Role.ADMINISTRATOR:
            return qs
        return qs.filter(Q(owner=user) | Q(owner__isnull=True))

    def retrieve(self, request: Request, *args, **kwargs) -> Response:
        return Response({"success": True, "data": self.get_serializer(self.get_object()).data})

    def update(self, request: Request, *args, **kwargs) -> Response:
        partial = kwargs.pop("partial", False)
        instance = self.get_object()
        if request.user.role == User.Role.RESELLER and instance.owner_id != request.user.pk:
            return Response(status=status.HTTP_403_FORBIDDEN)
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response({"success": True, "data": serializer.data})

    def destroy(self, request: Request, *args, **kwargs) -> Response:
        instance = self.get_object()
        if instance.assignments.exists():
            return Response(
                {
                    "success": False,
                    "error": {
                        "code": "in_use",
                        "message": "Package assigné à des comptes — désactivez-le plutôt.",
                    },
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        if request.user.role == User.Role.RESELLER and instance.owner_id != request.user.pk:
            return Response(status=status.HTTP_403_FORBIDDEN)
        instance.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class AssignPackageView(APIView):
    permission_classes = [IsAuthenticated, IsResellerOrAdmin]

    def post(self, request: Request) -> Response:
        serializer = AssignPackageSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            user = User.objects.get(pk=serializer.validated_data["user_id"])
            package = HostingPackage.objects.get(pk=serializer.validated_data["package_id"])
        except (User.DoesNotExist, HostingPackage.DoesNotExist):
            return Response(
                {"success": False, "error": {"code": "not_found", "message": "Compte ou package introuvable."}},
                status=status.HTTP_404_NOT_FOUND,
            )
        assignment = apply_package_to_user(
            user,
            package,
            assigned_by=request.user,
            notes=serializer.validated_data.get("notes", ""),
        )
        return Response({"success": True, "data": PackageAssignmentSerializer(assignment).data})


class SeedPackagesView(APIView):
    permission_classes = [IsAuthenticated, IsAdministrator]

    def post(self, request: Request) -> Response:
        created = seed_default_packages()
        return Response(
            {
                "success": True,
                "data": {
                    "created": HostingPackageSerializer(created, many=True).data,
                    "count": len(created),
                },
            }
        )


class MyPackageView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request) -> Response:
        assignment = (
            PackageAssignment.objects.filter(user=request.user)
            .select_related("package")
            .first()
        )
        if not assignment:
            return Response({"success": True, "data": None})
        return Response({"success": True, "data": PackageAssignmentSerializer(assignment).data})
