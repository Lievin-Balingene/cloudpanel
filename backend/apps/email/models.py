"""Modèles e-mail d'hébergement."""
from __future__ import annotations

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models
from django.utils import timezone

from apps.email.passwd import hash_password, verify_password


class MailDomain(models.Model):
    """Domaine mail géré (souvent lié à un Domain hébergé)."""

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="mail_domains",
    )
    name = models.CharField(max_length=255, unique=True, db_index=True)
    domain = models.OneToOneField(
        "domains.Domain",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="mail_domain",
    )
    is_active = models.BooleanField(default=True)
    catch_all = models.EmailField(blank=True, default="")
    max_quota_mb = models.PositiveIntegerField(default=1024)
    dkim_enabled = models.BooleanField(default=False)
    dkim_selector = models.CharField(max_length=63, default="default")
    dkim_private_key = models.TextField(blank=True, default="")
    dkim_public_key = models.TextField(blank=True, default="")
    spf_record = models.CharField(max_length=512, blank=True, default="")
    dmarc_policy = models.CharField(
        max_length=16,
        default="none",
        choices=(
            ("none", "none"),
            ("quarantine", "quarantine"),
            ("reject", "reject"),
        ),
    )
    dmarc_rua = models.EmailField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("name",)

    def __str__(self) -> str:
        return self.name


class Mailbox(models.Model):
    """Compte e-mail (boîte)."""

    mail_domain = models.ForeignKey(MailDomain, on_delete=models.CASCADE, related_name="mailboxes")
    local_part = models.CharField(max_length=64)
    password_hash = models.CharField(max_length=256)
    # Mot de passe chiffré (Fernet) pour SSO Roundcube style cPanel
    password_secret = models.TextField(blank=True, default="")
    quota_mb = models.PositiveIntegerField(default=250, validators=[MinValueValidator(1)])
    used_mb = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)
    is_suspended = models.BooleanField(default=False)
    maildir = models.CharField(max_length=512, blank=True, default="")
    notes = models.CharField(max_length=255, blank=True, default="")
    last_login_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("local_part",)
        unique_together = ("mail_domain", "local_part")
        indexes = [models.Index(fields=["mail_domain", "is_active"])]

    def __str__(self) -> str:
        return self.address

    @property
    def address(self) -> str:
        return f"{self.local_part}@{self.mail_domain.name}"

    @property
    def status(self) -> str:
        if self.is_suspended:
            return "suspended"
        if not self.is_active:
            return "inactive"
        return "active"

    def set_password(self, raw: str) -> None:
        # SHA512-CRYPT ($6$) — natif Dovecot / Postfix SASL
        from apps.databases.crypto import encrypt_secret

        self.password_hash = hash_password(raw)
        self.password_secret = encrypt_secret(raw)

    def check_password(self, raw: str) -> bool:
        return verify_password(raw, self.password_hash)

    def get_password_plain(self) -> str | None:
        from apps.databases.crypto import decrypt_secret

        return decrypt_secret(self.password_secret)


class MailForwarder(models.Model):
    """Redirection / alias e-mail."""

    mail_domain = models.ForeignKey(MailDomain, on_delete=models.CASCADE, related_name="forwarders")
    local_part = models.CharField(max_length=64)
    destinations = models.JSONField(
        default=list,
        help_text="Liste d'adresses de destination.",
    )
    keep_copy = models.BooleanField(
        default=False,
        help_text="Conserver une copie locale si une boîte existe.",
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ("mail_domain", "local_part")
        ordering = ("local_part",)

    def __str__(self) -> str:
        return f"{self.local_part}@{self.mail_domain.name}"

    @property
    def address(self) -> str:
        return f"{self.local_part}@{self.mail_domain.name}"


class Autoresponder(models.Model):
    """Répondeur automatique."""

    mailbox = models.OneToOneField(Mailbox, on_delete=models.CASCADE, related_name="autoresponder")
    is_active = models.BooleanField(default=False)
    subject = models.CharField(max_length=255, default="Absence du bureau")
    body = models.TextField(blank=True, default="")
    start_at = models.DateTimeField(null=True, blank=True)
    end_at = models.DateTimeField(null=True, blank=True)
    interval_hours = models.PositiveIntegerField(default=24)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self) -> str:
        return f"Autoresponder({self.mailbox.address})"

    @property
    def is_currently_active(self) -> bool:
        if not self.is_active:
            return False
        now = timezone.now()
        if self.start_at and now < self.start_at:
            return False
        if self.end_at and now > self.end_at:
            return False
        return True


class MailFilter(models.Model):
    """Filtre simple côté boîte."""

    class Action(models.TextChoices):
        DISCARD = "discard", "Supprimer"
        DELIVER = "deliver", "Délivrer dans dossier"
        FORWARD = "forward", "Transférer"
        STOP = "stop", "Arrêter"

    mailbox = models.ForeignKey(Mailbox, on_delete=models.CASCADE, related_name="filters")
    name = models.CharField(max_length=120)
    match_field = models.CharField(
        max_length=32,
        default="subject",
        choices=(
            ("subject", "Sujet"),
            ("from", "De"),
            ("to", "À"),
            ("body", "Corps"),
        ),
    )
    match_op = models.CharField(
        max_length=16,
        default="contains",
        choices=(
            ("contains", "Contient"),
            ("equals", "Égal"),
            ("startswith", "Commence par"),
        ),
    )
    match_value = models.CharField(max_length=255)
    action = models.CharField(max_length=16, choices=Action.choices, default=Action.DELIVER)
    action_value = models.CharField(max_length=255, blank=True, default="")
    is_active = models.BooleanField(default=True)
    priority = models.PositiveIntegerField(default=100)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("priority", "name")

    def __str__(self) -> str:
        return f"{self.mailbox.address}:{self.name}"


class MailingList(models.Model):
    """Liste de diffusion basique."""

    mail_domain = models.ForeignKey(MailDomain, on_delete=models.CASCADE, related_name="lists")
    local_part = models.CharField(max_length=64)
    members = models.JSONField(default=list)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("mail_domain", "local_part")

    def __str__(self) -> str:
        return f"{self.local_part}@{self.mail_domain.name}"

    @property
    def address(self) -> str:
        return f"{self.local_part}@{self.mail_domain.name}"
