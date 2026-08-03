from __future__ import annotations

from django.contrib import admin

from apps.email.models import (
    Autoresponder,
    Mailbox,
    MailDomain,
    MailFilter,
    MailForwarder,
    MailingList,
)


class MailboxInline(admin.TabularInline):
    model = Mailbox
    extra = 0
    readonly_fields = ("password_hash", "maildir")


@admin.register(MailDomain)
class MailDomainAdmin(admin.ModelAdmin):
    list_display = ("name", "owner", "is_active", "dkim_enabled", "dmarc_policy")
    search_fields = ("name", "owner__username")
    inlines = [MailboxInline]


@admin.register(Mailbox)
class MailboxAdmin(admin.ModelAdmin):
    list_display = ("local_part", "mail_domain", "quota_mb", "is_active", "is_suspended")
    list_filter = ("is_active", "is_suspended")
    search_fields = ("local_part", "mail_domain__name")


@admin.register(MailForwarder)
class MailForwarderAdmin(admin.ModelAdmin):
    list_display = ("local_part", "mail_domain", "is_active", "keep_copy")


@admin.register(Autoresponder)
class AutoresponderAdmin(admin.ModelAdmin):
    list_display = ("mailbox", "is_active", "subject")


@admin.register(MailFilter)
class MailFilterAdmin(admin.ModelAdmin):
    list_display = ("name", "mailbox", "action", "is_active", "priority")


@admin.register(MailingList)
class MailingListAdmin(admin.ModelAdmin):
    list_display = ("local_part", "mail_domain", "is_active")
