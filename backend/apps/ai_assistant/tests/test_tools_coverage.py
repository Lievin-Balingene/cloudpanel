"""Couverture tools panneau client (registre + intents mock)."""
from __future__ import annotations

import pytest

from apps.ai_assistant.providers import ChatMessage, ToolSpec
from apps.ai_assistant.providers.mock import MockProvider
from apps.ai_assistant.tools import ensure_tools_loaded, get_tool, list_tool_specs


REQUIRED_TOOLS = [
    "get_account_overview",
    "get_my_package",
    "get_security_status",
    "list_domains",
    "create_domain",
    "issue_ssl_certificate",
    "list_databases",
    "create_database",
    "list_cron_jobs",
    "create_cron_job",
    "list_wordpress_sites",
    "install_wordpress",
    "list_files",
    "read_file_content",
    "write_file",
    "list_ftp_accounts",
    "create_ftp_account",
    "list_backups",
    "create_backup",
    "restore_backup",
    "list_mailboxes",
    "create_mailbox",
    "list_dns_zones",
    "upsert_dns_record",
    "list_php_versions",
    "create_php_selector",
    "create_python_app",
    "delete_python_app",
    "list_git_repos",
    "clone_git_repository",
    "list_docker_containers",
    "create_docker_container",
    "get_k8s_overview",
    "apply_k8s_manifest",
    "stop_application",
    "start_application",
]


@pytest.mark.django_db
def test_client_panel_tools_registered():
    ensure_tools_loaded()
    specs = {t.name for t in list_tool_specs()}
    assert len(specs) >= 80
    missing = [n for n in REQUIRED_TOOLS if n not in specs]
    assert missing == [], f"Tools manquants: {missing}"
    assert get_tool("create_domain").dangerous is True
    assert get_tool("list_domains").dangerous is False
    assert get_tool("write_file").dangerous is True
    assert get_tool("restore_backup").dangerous is True


def test_mock_intents_panel_coverage():
    p = MockProvider()
    names = set(REQUIRED_TOOLS) | {
        "check_application_status",
        "get_deployment_logs",
        "analyze_deployment_error",
        "list_jail_commands",
        "search_account_files",
        "list_php_selectors",
        "get_deployment_context",
    }
    tools = [
        ToolSpec(name=n, description=n, parameters={"type": "object", "properties": {}})
        for n in names
    ]

    cases = [
        ("Montre la vue d'ensemble de mon compte", "get_account_overview"),
        ("Liste mes domaines", "list_domains"),
        ("Liste mes bases de données", "list_databases"),
        ("Liste mes tâches cron", "list_cron_jobs"),
        ("Liste mes sites wordpress", "list_wordpress_sites"),
        ("cree un nouveau site wordpress avec le sous domaine wp.7une.info", "list_domains"),
        ("Liste les fichiers à la racine", "list_files"),
        ("Liste mes comptes ftp", "list_ftp_accounts"),
        ("Liste mes sauvegardes", "list_backups"),
        ("Liste mes boîtes mail", "list_mailboxes"),
        ("Liste mes zones dns", "list_dns_zones"),
        ("Liste mes conteneurs docker", "list_docker_containers"),
        ("Montre kubernetes", "get_k8s_overview"),
        ("Stoppe mon application python", "check_application_status"),
    ]
    for prompt, expected in cases:
        r = p.chat([ChatMessage(role="user", content=prompt)], tools=tools)
        assert r.tool_calls, f"Aucun tool pour: {prompt}"
        assert r.tool_calls[0].name == expected, f"{prompt} → {r.tool_calls[0].name} ≠ {expected}"


def test_mock_wordpress_create_chains_install_when_domain_exists():
    from apps.ai_assistant.providers import ChatMessage, ToolSpec
    from apps.ai_assistant.providers.mock import MockProvider, _extract_hostname

    assert _extract_hostname("cree wp sur wp.7une.info") == "wp.7une.info"

    p = MockProvider()
    tools = [
        ToolSpec(name=n, description=n, parameters={"type": "object", "properties": {}})
        for n in ("list_domains", "list_wordpress_sites", "install_wordpress", "create_domain")
    ]
    # Marque install_wordpress comme dangereuse n'est pas requis pour le mock packing
    r = p.chat(
        [
            ChatMessage(
                role="user",
                content="cree un nouveau site wordpress avec le sous domaine wp.7une.info",
            ),
            ChatMessage(
                role="tool",
                name="list_domains",
                content='{"ok": true, "domains": [{"id": 11, "name": "7une.info"}, {"id": 42, "name": "wp.7une.info"}]}',
            ),
            ChatMessage(
                role="tool",
                name="list_wordpress_sites",
                content='{"ok": true, "sites": []}',
            ),
        ],
        tools=tools,
    )
    assert r.tool_calls
    assert r.tool_calls[0].name == "install_wordpress"
    assert r.tool_calls[0].arguments.get("domain_id") == 42


def test_mock_wordpress_create_chains_subdomain_when_missing():
    from apps.ai_assistant.providers import ChatMessage, ToolSpec
    from apps.ai_assistant.providers.mock import MockProvider

    p = MockProvider()
    tools = [
        ToolSpec(name=n, description=n, parameters={"type": "object", "properties": {}})
        for n in ("list_domains", "list_wordpress_sites", "install_wordpress", "create_domain")
    ]
    r = p.chat(
        [
            ChatMessage(
                role="user",
                content="cree un nouveau site wordpress avec le sous domaine wp.7une.info",
            ),
            ChatMessage(
                role="tool",
                name="list_domains",
                content='{"ok": true, "domains": [{"id": 11, "name": "7une.info"}]}',
            ),
            ChatMessage(
                role="tool",
                name="list_wordpress_sites",
                content='{"ok": true, "sites": []}',
            ),
        ],
        tools=tools,
    )
    assert r.tool_calls
    assert r.tool_calls[0].name == "create_domain"
    assert r.tool_calls[0].arguments.get("name") == "wp.7une.info"
    assert r.tool_calls[0].arguments.get("parent_id") == 11
    assert r.tool_calls[0].arguments.get("domain_type") == "subdomain"
