# File Manager — V-zone Panel

## Sécurité

- Jail filesystem dans `VZONE_HOME_ROOT/<username>`
- Admins : accès à tout `VZONE_HOME_ROOT` (home personnel dans `admin/`)
- Protection path traversal (`..`) et zip/tar slip

## Arborescence (style cPanel)

Les comptes vivent sous **`/home/<username>/`** (comme cPanel) :

```
/home/
  admin/                 # home panneau admin
  monclient/
    public_html/
    www → public_html
    domains/
    mail/
    etc/
    ssl/
    logs/
    tmp/
    .trash/
```

Si `ls /home` est vide alors que des comptes existent, exécutez :

```bash
sudo bash scripts/migrate-homes-cpanel.sh
sudo systemctl restart vzone-api vzone-worker vzone-beat
```

Champs renseignés : `system_username`, `home_directory`.
Les boîtes mail vivent sous `mail/<domaine>/<utilisateur>/` (Maildir).

## Fonctions

Liste, mkdir, create, read/write (éditeur), upload, download, delete, rename, copy, move, chmod, compress (zip/tar.gz), decompress, search, preview.

## API

Préfixe : `/api/v1/files/`

Limites : édition 2 Mo, upload 128 Mo.

## UI

- WHM : `/whm/files`
- Client : `/panel/files`
- Drag & drop upload, presse-papiers copier/couper/coller, éditeur modal
