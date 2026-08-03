"""Factories pour les tests."""
from __future__ import annotations

import factory
from django.contrib.auth import get_user_model

from apps.accounts.models import ResourceQuota

User = get_user_model()


class UserFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = User

    email = factory.Sequence(lambda n: f"user{n}@vzone.test")
    username = factory.Sequence(lambda n: f"user{n}")
    role = User.Role.CLIENT
    is_active = True

    @factory.post_generation
    def password(self, create, extracted, **kwargs):  # type: ignore[no-untyped-def]
        pwd = extracted or "TestPassword123!"
        self.set_password(pwd)
        if create:
            self.save()
            ResourceQuota.objects.get_or_create(user=self)


class AdminFactory(UserFactory):
    role = User.Role.ADMINISTRATOR
    is_staff = True
    is_superuser = True
    email = factory.Sequence(lambda n: f"admin{n}@vzone.test")
    username = factory.Sequence(lambda n: f"admin{n}")


class ResellerFactory(UserFactory):
    role = User.Role.RESELLER
    email = factory.Sequence(lambda n: f"reseller{n}@vzone.test")
    username = factory.Sequence(lambda n: f"reseller{n}")
