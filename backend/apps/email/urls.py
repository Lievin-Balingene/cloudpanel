from __future__ import annotations

from django.urls import path

from apps.email.views import (
    EmailOverviewView,
    ForwarderDeleteView,
    ForwarderListCreateView,
    MailboxAutoresponderView,
    MailboxDetailView,
    MailboxFilterListCreateView,
    MailboxListCreateView,
    MailboxSuspendView,
    MailDkimEnableView,
    MailDmarcUpdateView,
    MailDnsSyncView,
    MailDomainDetailView,
    MailDomainListCreateView,
    MailFilterDeleteView,
    MailingListListCreateView,
)

urlpatterns = [
    path("overview/", EmailOverviewView.as_view(), name="email-overview"),
    path("domains/", MailDomainListCreateView.as_view(), name="email-domain-list"),
    path("domains/<int:pk>/", MailDomainDetailView.as_view(), name="email-domain-detail"),
    path("domains/<int:pk>/dns-sync/", MailDnsSyncView.as_view(), name="email-dns-sync"),
    path("domains/<int:pk>/dkim/", MailDkimEnableView.as_view(), name="email-dkim"),
    path("domains/<int:pk>/dmarc/", MailDmarcUpdateView.as_view(), name="email-dmarc"),
    path("mailboxes/", MailboxListCreateView.as_view(), name="email-mailbox-list"),
    path("mailboxes/<int:pk>/", MailboxDetailView.as_view(), name="email-mailbox-detail"),
    path("mailboxes/<int:pk>/suspend/", MailboxSuspendView.as_view(), name="email-mailbox-suspend"),
    path(
        "mailboxes/<int:pk>/autoresponder/",
        MailboxAutoresponderView.as_view(),
        name="email-autoresponder",
    ),
    path(
        "mailboxes/<int:pk>/filters/",
        MailboxFilterListCreateView.as_view(),
        name="email-filter-list",
    ),
    path(
        "mailboxes/<int:pk>/filters/<int:filter_id>/",
        MailFilterDeleteView.as_view(),
        name="email-filter-delete",
    ),
    path("forwarders/", ForwarderListCreateView.as_view(), name="email-forwarder-list"),
    path("forwarders/<int:pk>/", ForwarderDeleteView.as_view(), name="email-forwarder-delete"),
    path("lists/", MailingListListCreateView.as_view(), name="email-list-list"),
]
