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
    "inspect_project_folder",
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


def test_mock_wordpress_multiturn_hostname_then_go():
    """Hostname seul après demande WP, puis « vas-y » → enchaîne install."""
    from apps.ai_assistant.providers import ChatMessage, ToolSpec
    from apps.ai_assistant.providers.mock import MockProvider

    p = MockProvider()
    tools = [
        ToolSpec(name=n, description=n, parameters={"type": "object", "properties": {}})
        for n in ("list_domains", "list_wordpress_sites", "install_wordpress", "create_domain")
    ]

    # Tour 1 : intention sans hostname → liste
    r1 = p.chat(
        [ChatMessage(role="user", content="cree une app wordpress")],
        tools=tools,
    )
    assert {c.name for c in r1.tool_calls} >= {"list_domains", "list_wordpress_sites"}

    # Après list sans host → demande le domaine
    r_ask = p.chat(
        [
            ChatMessage(role="user", content="cree une app wordpress"),
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
    assert not r_ask.tool_calls
    assert "domaine" in (r_ask.content or "").lower()

    # Tour 2 : hostname seul
    r2 = p.chat(
        [
            ChatMessage(role="user", content="cree une app wordpress"),
            ChatMessage(
                role="assistant",
                content=r_ask.content or "Pour installer WordPress, indique le domaine ou sous-domaine cible.",
            ),
            ChatMessage(role="user", content="le sous domaine c'est wp.7une.info"),
        ],
        tools=tools,
    )
    assert r2.tool_calls
    assert {c.name for c in r2.tool_calls} >= {"list_domains", "list_wordpress_sites"}

    # Après list avec host → create_domain
    r3 = p.chat(
        [
            ChatMessage(role="user", content="cree une app wordpress"),
            ChatMessage(
                role="assistant",
                content="Pour installer WordPress, indique le domaine ou sous-domaine cible.",
            ),
            ChatMessage(role="user", content="le sous domaine c'est wp.7une.info"),
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
    assert r3.tool_calls
    assert r3.tool_calls[0].name == "create_domain"
    assert r3.tool_calls[0].arguments.get("name") == "wp.7une.info"

    # « vas y agis » si host déjà donné
    r4 = p.chat(
        [
            ChatMessage(role="user", content="cree une app wordpress"),
            ChatMessage(
                role="assistant",
                content="Pour installer WordPress, indique le domaine ou sous-domaine cible.",
            ),
            ChatMessage(role="user", content="le sous domaine c'est wp.7une.info"),
            ChatMessage(role="user", content="vas y agis"),
        ],
        tools=tools,
    )
    assert r4.tool_calls
    assert {c.name for c in r4.tool_calls} >= {"list_domains", "list_wordpress_sites"}


def test_mock_wordpress_typo_wordpresse():
    from apps.ai_assistant.providers import ChatMessage, ToolSpec
    from apps.ai_assistant.providers.mock import MockProvider

    p = MockProvider()
    tools = [
        ToolSpec(name=n, description=n, parameters={"type": "object", "properties": {}})
        for n in ("list_domains", "list_wordpress_sites", "install_wordpress")
    ]
    r = p.chat(
        [
            ChatMessage(
                role="user",
                content="cree un site wordpresse maintenant sur le sous domaine wp.7une.info",
            )
        ],
        tools=tools,
    )
    assert r.tool_calls
    assert r.tool_calls[0].name == "list_domains"


def test_mock_knows_username_from_context():
    from apps.ai_assistant.providers import ChatMessage
    from apps.ai_assistant.providers.mock import MockProvider

    p = MockProvider()
    r = p.chat(
        [
            ChatMessage(
                role="system",
                content='Contexte session\n{"username": "lievin", "role": "client"}',
            ),
            ChatMessage(role="user", content="tu connais mon nom??"),
        ],
        tools=[],
    )
    assert "lievin" in (r.content or "").lower()
    assert not r.tool_calls


def test_mock_create_file_write_file():
    from apps.ai_assistant.providers import ChatMessage, ToolSpec
    from apps.ai_assistant.providers.mock import MockProvider, _extract_path_name

    assert _extract_path_name("cree un fichier du nom lievin.txt", kind="file") == "lievin.txt"

    p = MockProvider()
    tools = [
        ToolSpec(name=n, description=n, parameters={"type": "object", "properties": {}})
        for n in ("list_files", "write_file", "mkdir_path", "delete_paths")
    ]
    r = p.chat(
        [ChatMessage(role="user", content="cree un fichier du nom lievin.txt")],
        tools=tools,
    )
    assert r.tool_calls
    assert r.tool_calls[0].name == "write_file"
    assert r.tool_calls[0].arguments.get("path") == "lievin.txt"
    assert r.tool_calls[0].arguments.get("content") == ""

    r2 = p.chat(
        [ChatMessage(role="user", content="crée un dossier logs")],
        tools=tools,
    )
    assert r2.tool_calls
    assert r2.tool_calls[0].name == "mkdir_path"
    assert r2.tool_calls[0].arguments.get("path") == "logs"


def test_mock_email_page_help_not_python_logs():
    """Le JSON `python_apps` ne doit pas déclencher les logs Python sur la page Email."""
    from apps.ai_assistant.providers import ChatMessage, ToolSpec
    from apps.ai_assistant.providers.mock import MockProvider

    p = MockProvider()
    tools = [
        ToolSpec(name=n, description=n, parameters={"type": "object", "properties": {}})
        for n in (
            "list_mailboxes",
            "create_mailbox",
            "check_application_status",
            "get_page_logs",
            "analyze_deployment_error",
            "get_account_overview",
            "get_deployment_context",
        )
    ]
    sys_msg = (
        "Page actuelle: Email (/panel/email)\n"
        "Portail: client\n"
        "Besoin immédiat: Comptes mail.\n"
        "Tools suggérées: list_mailboxes\n"
        "Runtime page: n/a\n"
        "Adapte ta première réponse à cette page.\n"
        '{"username":"lievin","python_apps":[{"id":4,"name":"vzone"}]}'
    )
    r = p.chat(
        [
            ChatMessage(role="system", content=sys_msg),
            ChatMessage(
                role="user",
                content="Je suis sur la page Email. Comptes mail. Aide-moi.",
            ),
        ],
        tools=tools,
    )
    assert r.tool_calls
    assert r.tool_calls[0].name == "list_mailboxes"
    assert {c.name for c in r.tool_calls} == {"list_mailboxes"}


def test_mock_list_mailboxes_not_hijacked_by_file_manager_page():
    from apps.ai_assistant.providers import ChatMessage, ToolSpec
    from apps.ai_assistant.providers.mock import MockProvider

    p = MockProvider()
    tools = [
        ToolSpec(name=n, description=n, parameters={"type": "object", "properties": {}})
        for n in ("list_mailboxes", "list_files", "write_file")
    ]
    sys_msg = (
        "Page actuelle: File Manager (/panel/files)\n"
        "Portail: client\n"
        "Besoin immédiat: Fichiers home.\n"
        "Tools suggérées: list_files\n"
        "Runtime page: n/a\n"
    )
    for prompt in (
        "Liste mes boîtes mail",
        "montre mes emails",
        "affiche la messagerie",
    ):
        r = p.chat(
            [
                ChatMessage(role="system", content=sys_msg),
                ChatMessage(role="user", content=prompt),
            ],
            tools=tools,
        )
        assert r.tool_calls, prompt
        assert r.tool_calls[0].name == "list_mailboxes", f"{prompt} → {r.tool_calls[0].name}"


def test_mock_django_deploy_from_folder_flow():
    from apps.ai_assistant.providers import ChatMessage, ToolSpec
    from apps.ai_assistant.providers.mock import (
        MockProvider,
        _extract_project_folder,
        _wants_django_deploy,
    )

    assert _wants_django_deploy("peux tu deployer une nouvelle app django depuis zero??")
    assert _extract_project_folder("le dossier vzone contient le projet a deployer") == "vzone"

    p = MockProvider()
    tools = [
        ToolSpec(name=n, description=n, parameters={"type": "object", "properties": {}})
        for n in (
            "check_application_status",
            "list_domains",
            "list_files",
            "inspect_project_folder",
            "create_python_app",
            "install_dependencies",
            "start_application",
            "list_mailboxes",
        )
    ]

    r1 = p.chat(
        [ChatMessage(role="user", content="peux tu deployer une nouvelle app django depuis zero??")],
        tools=tools,
    )
    assert r1.tool_calls
    names = {c.name for c in r1.tool_calls}
    assert "check_application_status" in names
    assert "list_domains" in names

    sys_pending = (
        'Contexte\n{"pending_deploy": true, "pending_deploy_root": "", "username": "lievin"}'
    )
    r2 = p.chat(
        [
            ChatMessage(role="system", content=sys_pending),
            ChatMessage(role="user", content="peux tu deployer une nouvelle app django depuis zero??"),
            ChatMessage(
                role="assistant",
                content="Compris — déploiement Django. Je vérifie…",
            ),
            ChatMessage(role="user", content="le dossier vzone contient le projet a deployer"),
            ChatMessage(
                role="tool",
                name="check_application_status",
                content='{"ok":true,"python_apps":[],"node_apps":[]}',
            ),
            ChatMessage(
                role="tool",
                name="list_domains",
                content='{"ok":true,"domains":[{"id":1,"name":"vzone.7une.info"},{"id":2,"name":"7une.info"}]}',
            ),
            ChatMessage(
                role="tool",
                name="list_files",
                content='{"ok":true,"result":{"cwd":"","entries":[{"name":"vzone","is_dir":true}]}}',
            ),
        ],
        tools=tools,
    )
    # Root connu → inspecte le dossier avant de demander le domaine
    assert r2.tool_calls
    assert r2.tool_calls[0].name == "inspect_project_folder"
    assert r2.tool_calls[0].arguments.get("path") == "vzone"

    r3 = p.chat(
        [
            ChatMessage(
                role="system",
                content='{"pending_deploy": true, "pending_deploy_root": "vzone"}',
            ),
            ChatMessage(role="user", content="deploy django"),
            ChatMessage(role="user", content="le dossier vzone contient le projet"),
            ChatMessage(role="user", content="domaine vzone.7une.info"),
            ChatMessage(
                role="tool",
                name="check_application_status",
                content='{"ok":true,"python_apps":[],"node_apps":[]}',
            ),
            ChatMessage(
                role="tool",
                name="list_domains",
                content='{"ok":true,"domains":[{"id":1,"name":"vzone.7une.info"}]}',
            ),
            ChatMessage(
                role="tool",
                name="inspect_project_folder",
                content=(
                    '{"ok":true,"path":"vzone","framework":"django","runtime":"python",'
                    '"mode":"wsgi","confidence":0.95,"signals":["manage.py"],'
                    '"entrypoint_suggested":"passenger_wsgi.py","summary":"django (python/wsgi)"}'
                ),
            ),
            ChatMessage(
                role="tool",
                name="list_files",
                content='{"ok":true,"entries":[{"name":"manage.py","is_dir":false}]}',
            ),
        ],
        tools=tools,
    )
    assert r3.tool_calls
    assert r3.tool_calls[0].name == "create_python_app"
    assert r3.tool_calls[0].arguments.get("relative_root") == "vzone"
    assert r3.tool_calls[0].arguments.get("framework") == "django"
    assert r3.tool_calls[0].arguments.get("domain_name") == "vzone.7une.info"


def test_mock_howto_python_deploy_not_auto_deploy():
    from apps.ai_assistant.providers import ChatMessage, ToolSpec
    from apps.ai_assistant.providers.mock import (
        MockProvider,
        _is_howto_or_explain,
        _wants_django_deploy,
    )

    q = "c'est un probleme cq explique moi comment mettre en ligne une app Python"
    assert _is_howto_or_explain(q)
    assert not _wants_django_deploy(q)

    p = MockProvider()
    tools = [
        ToolSpec(name=n, description=n, parameters={"type": "object", "properties": {}})
        for n in (
            "check_application_status",
            "list_domains",
            "list_files",
            "inspect_project_folder",
            "create_python_app",
        )
    ]
    r = p.chat([ChatMessage(role="user", content=q)], tools=tools)
    assert not r.tool_calls
    low = (r.content or "").lower()
    assert "mettre en ligne" in low or "create_python_app" in low or "dépendances" in low
    assert "dossiers visibles" not in low


def test_mock_inspect_project_folder_intent():
    from apps.ai_assistant.providers import ChatMessage, ToolSpec
    from apps.ai_assistant.providers.mock import MockProvider

    p = MockProvider()
    tools = [
        ToolSpec(name=n, description=n, parameters={"type": "object", "properties": {}})
        for n in ("inspect_project_folder", "list_files", "list_domains")
    ]
    r = p.chat(
        [ChatMessage(role="user", content="analyse le dossier vzone, c'est un projet django ?")],
        tools=tools,
    )
    assert r.tool_calls
    assert r.tool_calls[0].name == "inspect_project_folder"
    assert r.tool_calls[0].arguments.get("path") == "vzone"



def test_mock_message_beats_page_for_domains_and_apps():
    from apps.ai_assistant.providers import ChatMessage, ToolSpec
    from apps.ai_assistant.providers.mock import MockProvider

    p = MockProvider()
    tools = [
        ToolSpec(name=n, description=n, parameters={"type": "object", "properties": {}})
        for n in ("list_domains", "list_files", "check_application_status", "list_mailboxes")
    ]
    sys_files = (
        "Page actuelle: File Manager (/panel/files)\n"
        "Besoin immédiat: Fichiers.\nRuntime page: n/a\n"
    )
    r = p.chat(
        [
            ChatMessage(role="system", content=sys_files),
            ChatMessage(role="user", content="Montre mes domaines"),
        ],
        tools=tools,
    )
    assert r.tool_calls[0].name == "list_domains"

    r2 = p.chat(
        [
            ChatMessage(role="system", content=sys_files),
            ChatMessage(role="user", content="Liste mes applications python"),
        ],
        tools=tools,
    )
    assert r2.tool_calls[0].name == "check_application_status"


def test_mock_apps_running_not_account_dump():
    """« Quelles apps tournent sur mon compte ? » → apps only, pas overview/context."""
    from apps.ai_assistant.providers import ChatMessage, ToolSpec
    from apps.ai_assistant.providers.mock import MockProvider, _synthesize_tools

    p = MockProvider()
    tools = [
        ToolSpec(name=n, description=n, parameters={"type": "object", "properties": {}})
        for n in (
            "check_application_status",
            "get_account_overview",
            "get_deployment_context",
            "list_mailboxes",
        )
    ]
    r = p.chat(
        [ChatMessage(role="user", content="Quelles apps tournent sur mon compte ?")],
        tools=tools,
    )
    assert r.tool_calls
    names = [c.name for c in r.tool_calls]
    assert names == ["check_application_status"]

    body = _synthesize_tools(
        [
            ChatMessage(role="user", content="Quelles apps tournent sur mon compte ?"),
            ChatMessage(
                role="tool",
                name="get_account_overview",
                content=(
                    '{"ok":true,"account":{"username":"lievin"},"my_package":"basique",'
                    '"disk":{"used_mb":1,"quota_mb":10,"percent":1},"usage":{"domains":1}}'
                ),
            ),
            ChatMessage(
                role="tool",
                name="get_deployment_context",
                content='{"ok":true,"context":{}}',
            ),
            ChatMessage(
                role="tool",
                name="check_application_status",
                content=(
                    '{"ok":true,"python_apps":[{"id":4,"name":"vzone","status":"running",'
                    '"port":8100,"domain":"vzone.7une.info"}],"node_apps":[]}'
                ),
            ),
        ]
    )
    assert "Voici tes applications" in body
    assert "vzone" in body
    assert "Vue d" not in body
    assert "champs :" not in body
    assert "get_deployment_context" not in body


def test_mock_issue_ssl_on_domain_flow():
    from apps.ai_assistant.providers import ChatMessage, ToolSpec
    from apps.ai_assistant.providers.mock import MockProvider, _wants_ssl_issue

    assert _wants_ssl_issue("installe le certificat ssl sur 7une.info")

    p = MockProvider()
    tools = [
        ToolSpec(name=n, description=n, parameters={"type": "object", "properties": {}})
        for n in ("list_domains", "issue_ssl_certificate", "list_files", "check_application_status")
    ]
    r1 = p.chat(
        [ChatMessage(role="user", content="installe le certificat ssl sur 7une.info")],
        tools=tools,
    )
    assert r1.tool_calls
    assert r1.tool_calls[0].name == "list_domains"
    assert "ssl" in (r1.content or "").lower() or "certificat" in (r1.content or "").lower()

    r2 = p.chat(
        [
            ChatMessage(role="user", content="installe le certificat ssl sur 7une.info"),
            ChatMessage(
                role="assistant",
                content="Compris — certificat SSL / Let's Encrypt pour 7une.info…",
            ),
            ChatMessage(
                role="tool",
                name="list_domains",
                content=(
                    '{"ok":true,"domains":['
                    '{"id":4,"name":"7une.info","ssl":false},'
                    '{"id":7,"name":"vzone.7une.info","ssl":true}'
                    "]}"
                ),
            ),
        ],
        tools=tools,
    )
    assert r2.tool_calls
    assert r2.tool_calls[0].name == "issue_ssl_certificate"
    assert r2.tool_calls[0].arguments.get("domain_id") == 4


def test_mock_lance_commande_ls_is_jail_not_start_app():
    from apps.ai_assistant.providers import ChatMessage, ToolSpec
    from apps.ai_assistant.providers.mock import MockProvider, _resolve_jail_command_id

    assert _resolve_jail_command_id("lance une commande ls") == "ls_home"

    p = MockProvider()
    tools = [
        ToolSpec(name=n, description=n, parameters={"type": "object", "properties": {}})
        for n in (
            "run_jail_command",
            "list_jail_commands",
            "start_application",
            "check_application_status",
        )
    ]
    r = p.chat(
        [ChatMessage(role="user", content="lance une commande ls")],
        tools=tools,
    )
    assert r.tool_calls
    assert len(r.tool_calls) == 1
    assert r.tool_calls[0].name == "run_jail_command"
    assert r.tool_calls[0].arguments.get("command_id") == "ls_home"


def test_mock_create_mailbox_flow():
    from apps.ai_assistant.providers import ChatMessage, ToolSpec
    from apps.ai_assistant.providers.mock import MockProvider

    p = MockProvider()
    tools = [
        ToolSpec(name=n, description=n, parameters={"type": "object", "properties": {}})
        for n in ("list_mailboxes", "create_mailbox", "get_account_overview", "get_deployment_context")
    ]
    r1 = p.chat(
        [ChatMessage(role="user", content="cree un nouveua compte de messagerie")],
        tools=tools,
    )
    assert r1.tool_calls
    assert r1.tool_calls[0].name == "list_mailboxes"

    r2 = p.chat(
        [
            ChatMessage(role="user", content="cree un nouveua compte de messagerie"),
            ChatMessage(
                role="tool",
                name="list_mailboxes",
                content='{"ok":true,"domains":[{"id":1,"name":"7une.info"}],"mailboxes":[]}',
            ),
        ],
        tools=tools,
    )
    assert not r2.tool_calls
    assert "mot de passe" in (r2.content or "").lower() or "adresse" in (r2.content or "").lower()

    r3 = p.chat(
        [
            ChatMessage(
                role="user",
                content="crée contact@7une.info mot de passe Secret1234",
            ),
            ChatMessage(
                role="tool",
                name="list_mailboxes",
                content='{"ok":true,"domains":[{"id":1,"name":"7une.info"}],"mailboxes":[]}',
            ),
        ],
        tools=tools,
    )
    assert r3.tool_calls
    assert r3.tool_calls[0].name == "create_mailbox"
    assert r3.tool_calls[0].arguments.get("local_part") == "contact"
    assert r3.tool_calls[0].arguments.get("mail_domain_id") == 1
    assert r3.tool_calls[0].arguments.get("password") == "Secret1234"
