# Generated manually for server_setup

from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name="ServerSetup",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("hostname", models.CharField(blank=True, default="", max_length=255)),
                ("nameserver1", models.CharField(blank=True, default="", max_length=255)),
                ("nameserver2", models.CharField(blank=True, default="", max_length=255)),
                ("nameserver3", models.CharField(blank=True, default="", max_length=255)),
                ("nameserver4", models.CharField(blank=True, default="", max_length=255)),
                ("resolver1", models.GenericIPAddressField(blank=True, null=True)),
                ("resolver2", models.GenericIPAddressField(blank=True, null=True)),
                ("contact_email", models.EmailField(blank=True, default="", max_length=254)),
                ("apply_hostname_to_mail", models.BooleanField(default=True)),
                ("last_hostname_error", models.TextField(blank=True, default="")),
                ("hostname_applied_at", models.DateTimeField(blank=True, null=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
            ],
            options={
                "verbose_name": "Configuration serveur",
                "verbose_name_plural": "Configuration serveur",
            },
        ),
    ]
