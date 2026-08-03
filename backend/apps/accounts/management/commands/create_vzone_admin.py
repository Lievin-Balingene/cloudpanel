"""Commande : créer l'administrateur initial en non-interactif."""
from __future__ import annotations

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Crée un administrateur V-zone (idempotent)."

    def add_arguments(self, parser) -> None:  # type: ignore[no-untyped-def]
        parser.add_argument("--email", required=True)
        parser.add_argument("--username", default="admin")
        parser.add_argument("--password", required=True)
        parser.add_argument(
            "--must-change-password",
            action="store_true",
            help="Force le changement de mot de passe à la prochaine connexion.",
        )

    def handle(self, *args, **options) -> None:
        User = get_user_model()
        username = options["username"]
        if User.objects.filter(username=username).exists():
            self.stdout.write(self.style.WARNING(f"Utilisateur {username} déjà présent."))
            return
        try:
            user = User.objects.create_superuser(
                email=options["email"],
                username=username,
                password=options["password"],
            )
        except Exception as exc:  # noqa: BLE001
            raise CommandError(str(exc)) from exc
        if options["must_change_password"]:
            user.must_change_password = True
            user.save(update_fields=["must_change_password"])
        self.stdout.write(self.style.SUCCESS(f"Administrateur {username} créé."))
