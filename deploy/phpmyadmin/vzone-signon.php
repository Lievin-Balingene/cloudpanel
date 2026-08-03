<?php
/**
 * Formulaire de connexion MySQL (accès manuel /phpmyadmin/).
 */
declare(strict_types=1);

session_name('VzonePmaSignon');
session_start();

if (isset($_GET['logout'])) {
    $_SESSION = [];
    session_destroy();
}

$error = '';
if ($_SERVER['REQUEST_METHOD'] === 'POST') {
    $user = trim((string)($_POST['pma_username'] ?? ''));
    $pass = (string)($_POST['pma_password'] ?? '');
    if ($user === '') {
        $error = 'Identifiant requis.';
    } else {
        $_SESSION['PMA_single_signon_user'] = $user;
        $_SESSION['PMA_single_signon_password'] = $pass;
        $_SESSION['PMA_single_signon_host'] = 'localhost';
        header('Location: index.php');
        exit;
    }
}
?><!DOCTYPE html>
<html lang="fr">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>phpMyAdmin — V-zone</title>
  <style>
    body { font-family: system-ui, sans-serif; background: #f5f5f5; margin: 0; display: grid; place-items: center; min-height: 100vh; }
    .box { background: #fff; border: 1px solid #ddd; border-radius: 8px; padding: 2rem; width: min(360px, 92vw); box-shadow: 0 8px 24px rgba(0,0,0,.06); }
    h1 { margin: 0 0 .25rem; font-size: 1.25rem; color: #1a2b4a; }
    p { color: #666; font-size: .9rem; margin: 0 0 1.25rem; }
    label { display: block; font-size: .8rem; font-weight: 600; margin: .75rem 0 .25rem; }
    input { width: 100%; padding: .55rem .65rem; border: 1px solid #ccc; border-radius: 6px; box-sizing: border-box; }
    button { margin-top: 1.25rem; width: 100%; padding: .65rem; border: 0; border-radius: 6px; background: #152536; color: #fff; font-weight: 600; cursor: pointer; }
    .err { color: #b00020; font-size: .85rem; margin-top: .75rem; }
  </style>
</head>
<body>
  <form class="box" method="post" action="vzone-signon.php">
    <h1>phpMyAdmin</h1>
    <p>Connectez-vous avec un utilisateur MySQL du panel (comme cPanel).</p>
    <label for="u">Utilisateur MySQL</label>
    <input id="u" name="pma_username" autocomplete="username" required>
    <label for="p">Mot de passe</label>
    <input id="p" type="password" name="pma_password" autocomplete="current-password">
    <?php if ($error): ?><div class="err"><?= htmlspecialchars($error) ?></div><?php endif; ?>
    <button type="submit">Se connecter</button>
  </form>
</body>
</html>
