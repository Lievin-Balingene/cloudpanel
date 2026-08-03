"""API bases de données."""
from __future__ import annotations

from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.models import User
from apps.databases.serializers import (
    DatabaseCreateSerializer,
    DatabasePrivilegeCreateSerializer,
    DatabasePrivilegeSerializer,
    DatabaseSerializer,
    DatabaseUserCreateSerializer,
    DatabaseUserSerializer,
    DatabaseUserUpdateSerializer,
)
from apps.databases.services import (
    create_database,
    create_database_user,
    databases_qs,
    db_users_qs,
    delete_database,
    delete_database_user,
    grant_privilege,
    overview_for,
    privileges_qs,
    revoke_privilege,
    update_database_user,
)


def _resolve_owner(request: Request, owner_id: int | None) -> User:
    owner = request.user
    if owner_id and request.user.role in {User.Role.ADMINISTRATOR, User.Role.RESELLER}:
        owner = get_object_or_404(User, pk=owner_id)
        if request.user.role == User.Role.RESELLER and owner.parent_id != request.user.pk:
            raise PermissionError
    return owner


class DatabaseOverviewView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request) -> Response:
        return Response({"success": True, "data": overview_for(request.user)})


class DatabaseListCreateView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request) -> Response:
        qs = databases_qs(request.user)
        engine = request.query_params.get("engine")
        if engine:
            qs = qs.filter(engine=engine)
        return Response({"success": True, "data": DatabaseSerializer(qs, many=True).data})

    def post(self, request: Request) -> Response:
        serializer = DatabaseCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        try:
            owner = _resolve_owner(request, data.get("owner_id"))
        except PermissionError:
            return Response(status=status.HTTP_403_FORBIDDEN)
        db = create_database(
            owner=owner,
            name=data["name"],
            engine=data.get("engine", "mysql"),
            charset=data.get("charset", "utf8mb4"),
            collation=data.get("collation", "utf8mb4_unicode_ci"),
            notes=data.get("notes", ""),
        )
        return Response(
            {"success": True, "data": DatabaseSerializer(db).data},
            status=status.HTTP_201_CREATED,
        )


class DatabaseDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request, pk: int) -> Response:
        db = get_object_or_404(databases_qs(request.user), pk=pk)
        return Response({"success": True, "data": DatabaseSerializer(db).data})

    def delete(self, request: Request, pk: int) -> Response:
        db = get_object_or_404(databases_qs(request.user), pk=pk)
        delete_database(db)
        return Response(status=status.HTTP_204_NO_CONTENT)


class DatabaseUserListCreateView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request) -> Response:
        qs = db_users_qs(request.user)
        engine = request.query_params.get("engine")
        if engine:
            qs = qs.filter(engine=engine)
        return Response({"success": True, "data": DatabaseUserSerializer(qs, many=True).data})

    def post(self, request: Request) -> Response:
        serializer = DatabaseUserCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        try:
            owner = _resolve_owner(request, data.get("owner_id"))
        except PermissionError:
            return Response(status=status.HTTP_403_FORBIDDEN)
        user = create_database_user(
            owner=owner,
            username=data["username"],
            password=data["password"],
            engine=data.get("engine", "mysql"),
            host=data.get("host", "localhost"),
            notes=data.get("notes", ""),
        )
        return Response(
            {"success": True, "data": DatabaseUserSerializer(user).data},
            status=status.HTTP_201_CREATED,
        )


class DatabaseUserDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request, pk: int) -> Response:
        user = get_object_or_404(db_users_qs(request.user), pk=pk)
        return Response({"success": True, "data": DatabaseUserSerializer(user).data})

    def patch(self, request: Request, pk: int) -> Response:
        user = get_object_or_404(db_users_qs(request.user), pk=pk)
        serializer = DatabaseUserUpdateSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        user = update_database_user(user, **serializer.validated_data)
        return Response({"success": True, "data": DatabaseUserSerializer(user).data})

    def delete(self, request: Request, pk: int) -> Response:
        user = get_object_or_404(db_users_qs(request.user), pk=pk)
        delete_database_user(user)
        return Response(status=status.HTTP_204_NO_CONTENT)


class PrivilegeListCreateView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request) -> Response:
        qs = privileges_qs(request.user)
        return Response({"success": True, "data": DatabasePrivilegeSerializer(qs, many=True).data})

    def post(self, request: Request) -> Response:
        serializer = DatabasePrivilegeCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        db = get_object_or_404(databases_qs(request.user), pk=data["database_id"])
        user = get_object_or_404(db_users_qs(request.user), pk=data["user_id"])
        priv = grant_privilege(database=db, user=user, privileges=data.get("privileges", "ALL"))
        return Response(
            {"success": True, "data": DatabasePrivilegeSerializer(priv).data},
            status=status.HTTP_201_CREATED,
        )


class PrivilegeDeleteView(APIView):
    permission_classes = [IsAuthenticated]

    def delete(self, request: Request, pk: int) -> Response:
        priv = get_object_or_404(privileges_qs(request.user), pk=pk)
        revoke_privilege(priv)
        return Response(status=status.HTTP_204_NO_CONTENT)
