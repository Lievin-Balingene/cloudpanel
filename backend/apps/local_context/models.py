"""Profil d'exploitation du panneau (réseau, fuseau, petit VPS) — pas de facturation."""
from __future__ import annotations

from django.db import models


class LocalSiteProfile(models.Model):
    """Une ligne : pays, fuseau, économie de data, fenêtre de nuit."""

    country = models.CharField(max_length=8, default="CD")
    timezone = models.CharField(max_length=64, default="Africa/Kinshasa")
    data_saver = models.BooleanField(
        default=False,
        help_text="Réduit le rafraîchissement du panneau (données mobiles chères / instables).",
    )
    lite_panel = models.BooleanField(
        default=False,
        help_text="Masque Docker / Kubernetes — pour un VPS 2–4 Go.",
    )
    require_phone = models.BooleanField(
        default=False,
        help_text="Numéro mobile à la création de compte (contact WhatsApp / SMS, pas de facture).",
    )
    phone_prefix = models.CharField(max_length=8, default="+243")
    notify_channel = models.CharField(max_length=16, default="whatsapp")
    backup_window_start = models.PositiveSmallIntegerField(default=1)
    backup_window_end = models.PositiveSmallIntegerField(default=6)
    defer_heavy_jobs = models.BooleanField(
        default=True,
        help_text="Repousse les sauvegardes planifiées la nuit (lien saturé le jour, coupures).",
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Profil local"

    def __str__(self) -> str:
        return f"LocalSiteProfile({self.country})"

    @classmethod
    def get_solo(cls) -> LocalSiteProfile:
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj
