# API jetons — style cPanel (WHM API 1 et UAPI)

AngaPanel expose une API externe authentifiée par **jeton**, sur le même modèle que cPanel / WHM :

- **WHM JSON API** pour l’administrateur et le revendeur (`listaccts`, `createacct`, DNS, packages…).
- **UAPI** pour le compte (`/execute/Module/fonction`) : domaines, e-mail, bases, FTP, cron, fichiers, PHP, sauvegardes.

Les fonctions appellent les mêmes services que l’interface (création de compte, boîte mail, base, zone DNS, etc.). Ce n’est pas une couche factice.

La gestion des jetons est dans le panneau :

- WHM : **Manage API Tokens** (`/whm/api`)
- Compte : **Jetons API** (`/panel/api`)

Le secret (`vzapi_…`) n’est affiché **qu’une fois**. Seul son empreinte SHA-256 est stockée.

## Authentification

```http
Authorization: whm UTILISATEUR:JETON
Authorization: cpanel UTILISATEUR:JETON
Authorization: anga UTILISATEUR:JETON
Authorization: Bearer vzapi_…
```

`UTILISATEUR` est le nom du compte propriétaire du jeton. Un jeton client ne peut pas appeler l’API WHM. Un jeton peut être limité à une liste de fonctions, à des IP / CIDR, et à une date d’expiration.

Révoquer un jeton le rend inutilisable immédiatement.

## WHM JSON API

```bash
curl -H "Authorization: whm root:JETON" \
  "https://panneau.example/api/json-api/listaccts"

curl -H "Authorization: whm root:JETON" \
  -H "Content-Type: application/json" \
  -d '{"username":"client1","domain":"exemple.com","password":"MotDePasse10!","contactemail":"a@exemple.com"}' \
  "https://panneau.example/api/json-api/createacct"
```

Réponse :

```json
{
  "metadata": { "version": 1, "result": 1, "reason": "OK", "command": "listaccts" },
  "data": { "acct": [] }
}
```

`result` vaut `0` si l’appel échoue (`reason` explique pourquoi). Un jeton absent ou faux répond `401`.

| Fonction | Rôle | Paramètres |
|----------|------|------------|
| `version` | Tous (jeton WHM) | — |
| `applist` | Tous (jeton WHM) | — |
| `listaccts` | list-accts | `search` |
| `accountsummary` | list-accts | `user` |
| `createacct` | create-acct | `username`, `domain`, `password`, `contactemail`, `plan` |
| `suspendacct` / `unsuspendacct` | suspend-acct | `user` |
| `passwd` | edit-account | `user`, `password` |
| `removeacct` | kill-acct | `user` |
| `listpkgs` | list-pkgs | — |
| `listzones` / `dumpzone` | manage-dns | `domain` |
| `addzonerecord` | manage-dns | `domain`, `type`, `name`, `address` |
| `servicestatus` | res-monitoring | — |
| `cpanel` | jeton WHM | `cpanel_jsonapi_user`, `cpanel_jsonapi_module`, `cpanel_jsonapi_func` |
| `apirequest` | list-accts | `method`, `path` (`/api/v1/…`), `data` |

Les privilèges sont ceux du revendeur (ACL). L’administrateur passe partout.

## UAPI

```bash
curl -H "Authorization: cpanel client1:JETON" \
  "https://panneau.example/api/execute/DomainInfo/list_domains"

curl -H "Authorization: cpanel client1:JETON" \
  -H "Content-Type: application/json" \
  -d '{"email":"info@exemple.com","password":"MotDePasse10!"}' \
  "https://panneau.example/api/execute/Email/add_pop"
```

Réponse :

```json
{
  "apiversion": 3,
  "module": "DomainInfo",
  "func": "list_domains",
  "result": { "status": 1, "data": {}, "errors": null }
}
```

Un admin ou un revendeur peut viser un compte enfant :

```bash
curl -H "Authorization: whm revendeur:JETON" \
  "https://panneau.example/api/execute/Email/list_pops?account=client1"
```

Le revendeur ne voit que ses propres clients. Un client ne peut pas passer `account`.

| Module.fonction | Effet |
|-----------------|--------|
| `Variables.get_user_information` | Identité du compte |
| `DomainInfo.list_domains` | Domaines |
| `DomainInfo.single_domain_data` | Détail (`domain`) |
| `Domain.add_domain` | Crée un domaine (`domain`, `type`, `rootdomain`, `dir`) |
| `Email.list_pops` / `add_pop` / `passwd_pop` / `delete_pop` | Boîtes mail |
| `Mysql.list_databases` / `create_database` / `delete_database` / `create_user` | MySQL ou PostgreSQL (`engine`) |
| `Ftp.list_ftp` / `add_ftp` / `delete_ftp` | Comptes FTP |
| `Cron.list_cron` / `add_line` / `remove_line` | Tâches cron |
| `DNS.list_zones` / `parse_zone` / `mass_edit_zone` | Zones et enregistrements |
| `Fileman.list_files` | Dossier du compte (`dir`) |
| `LangPHP.php_get_installed_versions` | Versions PHP |
| `Stats.get_stats` | Vue d’ensemble |
| `Backup.list_backups` | Archives |
| `Panel.request` | N'importe quelle route `/api/v1/…` du compte (`method`, `path`, `data`) |

`apirequest` (WHM) et `Panel.request` (UAPI) passent par les mêmes vues que l'interface, avec les droits du compte. On peut ainsi automatiser fichiers, SSL, WordPress, paquets, sauvegardes, etc.

```bash
curl -H "Authorization: whm root:JETON" \
  -H "Content-Type: application/json" \
  -d '{"method":"GET","path":"/api/v1/packages/"}' \
  "https://panneau.example/api/json-api/apirequest"

curl -H "Authorization: whm root:JETON" \
  "https://panneau.example/api/json-api/cpanel?cpanel_jsonapi_user=client1&cpanel_jsonapi_module=Email&cpanel_jsonapi_func=list_pops"
```

Les quotas, mots de passe et préfixes de bases sont ceux du panneau (les mêmes règles que l’interface).

## Gestion des jetons (session du panneau)

Ces routes utilisent le JWT de l’interface, pas le jeton externe.

| Méthode | Chemin | Description |
|---------|--------|-------------|
| GET | `/api/v1/api-tokens/` | Jetons du compte (sans le secret) |
| POST | `/api/v1/api-tokens/` | Créer. Corps : `name`, `audience` (`uapi`, `whm`, `both`), `scopes` (`["*"]` ou noms de fonctions), `ip_allowlist`, `expires_in_days` |
| DELETE | `/api/v1/api-tokens/<id>/` | Révoquer |
| GET | `/api/v1/api-tokens/catalog/` | Catalogue des fonctions |

Un compte client ne peut créer qu’un jeton `uapi`. Maximum 25 jetons actifs.
