# File Manager — V-zone Panel

## Sécurité

- Jail filesystem dans `VZONE_HOME_ROOT/<username>`
- Admins : accès à tout `VZONE_HOME_ROOT`
- Protection path traversal (`..`) et zip/tar slip

## Fonctions

Liste, mkdir, create, read/write (éditeur), upload, download, delete, rename, copy, move, chmod, compress (zip/tar.gz), decompress, search, preview.

## API

Préfixe : `/api/v1/files/`

Limites : édition 2 Mo, upload 128 Mo.

## UI

- WHM : `/whm/files`
- Client : `/panel/files`
- Drag & drop upload, presse-papiers copier/couper/coller, éditeur modal
