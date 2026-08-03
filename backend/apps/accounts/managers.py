"""Manager utilisateur personnalisé."""
from __future__ import annotations

from django.contrib.auth.base_user import BaseUserManager
from django.db import transaction


class UserManager(BaseUserManager):
    use_in_migrations = True

    def _create_user(self, email: str, username: str, password: str | None, **extra_fields):
        if not email:
            raise ValueError("L'adresse e-mail est obligatoire.")
        if not username:
            raise ValueError("Le nom d'utilisateur est obligatoire.")
        email = self.normalize_email(email)
        user = self.model(email=email, username=username, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_user(self, email: str, username: str, password: str | None = None, **extra_fields):
        extra_fields.setdefault("is_staff", False)
        extra_fields.setdefault("is_superuser", False)
        extra_fields.setdefault("role", "client")
        with transaction.atomic():
            user = self._create_user(email, username, password, **extra_fields)
            from apps.accounts.models import ResourceQuota

            ResourceQuota.objects.get_or_create(user=user)
        return user

    def create_superuser(
        self, email: str, username: str, password: str | None = None, **extra_fields
    ):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        extra_fields.setdefault("role", "administrator")
        if extra_fields.get("is_staff") is not True:
            raise ValueError("Le superutilisateur doit avoir is_staff=True.")
        if extra_fields.get("is_superuser") is not True:
            raise ValueError("Le superutilisateur doit avoir is_superuser=True.")
        with transaction.atomic():
            user = self._create_user(email, username, password, **extra_fields)
            from apps.accounts.models import ResourceQuota

            quota, _ = ResourceQuota.objects.get_or_create(user=user)
            quota.unlimited_disk = True
            quota.unlimited_cpu = True
            quota.unlimited_ram = True
            quota.emails = 0
            quota.databases = 0
            quota.domains = 0
            quota.ftp_accounts = 0
            quota.python_apps = 0
            quota.node_apps = 0
            quota.docker_containers = 0
            quota.save()
            try:
                from apps.accounts.services import provision_account_home

                provision_account_home(user)
            except Exception:  # noqa: BLE001
                pass
        return user
