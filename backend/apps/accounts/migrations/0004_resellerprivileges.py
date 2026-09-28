# Generated manually for ResellerPrivileges
from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0003_alter_user_two_factor_secret"),
    ]

    operations = [
        migrations.CreateModel(
            name="ResellerPrivileges",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                (
                    "privileges",
                    models.JSONField(
                        blank=True,
                        default=list,
                        help_text="Liste de codes privilege (create-acct, manage-dns, …).",
                    ),
                ),
                (
                    "enforce_ownership",
                    models.BooleanField(
                        default=True,
                        help_text="Les ressources des clients restent rattachees au revendeur (owner.parent).",
                    ),
                ),
                (
                    "allow_overselling",
                    models.BooleanField(
                        default=False,
                        help_text="Si false, les packages clients ne peuvent pas depasser le pool du revendeur.",
                    ),
                ),
                ("notes", models.CharField(blank=True, default="", max_length=255)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "updated_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="reseller_acl_updates",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "user",
                    models.OneToOneField(
                        limit_choices_to={"role": "reseller"},
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="reseller_privileges",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "verbose_name": "Privileges revendeur",
                "verbose_name_plural": "Privileges revendeurs",
            },
        ),
    ]
