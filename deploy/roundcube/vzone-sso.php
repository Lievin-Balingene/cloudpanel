<?php
/**
 * SSO one-shot V-zone Panel → Roundcube.
 * Token JSON : { "user", "password", "imap_host", "exp" }
 */
declare(strict_types=1);

header('Content-Type: text/plain; charset=utf-8');

$ssoDir = '__SSO_DIR__';
$token = preg_replace('/[^a-f0-9]/', '', (string)($_GET['t'] ?? ''));
if ($token === '' || strlen($token) < 32) {
    http_response_code(400);
    exit("Token invalide.\n");
}

$path = rtrim($ssoDir, '/') . '/' . $token . '.json';
if (!is_file($path) || !is_readable($path)) {
    http_response_code(403);
    exit(
        "Session expirée ou token illisible (droits SSO).\n" .
        "Rouvrez le webmail depuis le panel.\n" .
        "Réparez: sudo bash /opt/vzone-src/scripts/repair-mail-auth.sh\n"
    );
}

$raw = file_get_contents($path);
@unlink($path);
$data = json_decode((string)$raw, true);
if (!is_array($data) || empty($data['user']) || !array_key_exists('password', $data)) {
    http_response_code(403);
    exit("Token corrompu.\n");
}
if (!empty($data['exp']) && time() > (int)$data['exp']) {
    http_response_code(403);
    exit("Token expiré. Rouvrez le webmail depuis le panel.\n");
}

$user = trim((string)$data['user']);
$pass = (string)$data['password'];
$hostHint = trim((string)($data['imap_host'] ?? ''));

if ($user === '' || $pass === '') {
    http_response_code(403);
    exit("Identifiants vides dans le token. Réinitialisez le mot de passe de la boîte.\n");
}

define('INSTALL_PATH', rtrim(str_replace('\\', '/', __DIR__), '/') . '/');
require_once INSTALL_PATH . 'program/include/iniset.php';

/** @var rcmail $rcmail */
$rcmail = rcmail::get_instance();

// Nouvelle session propre
try {
    if (!empty($_SESSION['user_id'])) {
        $rcmail->logout_actions();
        $rcmail->kill_session();
    }
} catch (Throwable $e) {
    // ignore
}
try {
    $rcmail->session->start();
} catch (Throwable $e) {
    // ignore
}

// Hosts à essayer (IMAPS local d'abord — plus fiable avec ssl=yes Dovecot)
$hosts = [];
foreach ([
    $hostHint,
    'ssl://127.0.0.1:993',
    'ssl://localhost:993',
    '127.0.0.1:143',
    'localhost:143',
    'tls://127.0.0.1:143',
    null, // config Roundcube par défaut
] as $h) {
    if ($h === null) {
        if (!in_array(null, $hosts, true)) {
            $hosts[] = null;
        }
        continue;
    }
    $h = trim((string)$h);
    if ($h !== '' && !in_array($h, $hosts, true)) {
        $hosts[] = $h;
    }
}

$ok = false;
$errors = [];
foreach ($hosts as $host) {
    try {
        // Roundcube 1.6 : login($user, $pass, $host = null, $cookiecheck = false)
        $ok = (bool)$rcmail->login($user, $pass, $host, false);
        if ($ok) {
            break;
        }
        $err = '';
        if (!empty($rcmail->plugins)) {
            // best-effort
        }
        $errors[] = ($host === null ? '(config)' : $host) . ': login=false';
    } catch (Throwable $e) {
        $errors[] = ($host === null ? '(config)' : (string)$host) . ': ' . $e->getMessage();
        $ok = false;
    }
}

if ($ok) {
    if (method_exists($rcmail->session, 'write')) {
        $rcmail->session->write();
    }
    $target = './?_task=mail&_mbox=INBOX';
    try {
        if (method_exists($rcmail, 'url')) {
            $target = $rcmail->url(['_task' => 'mail', '_mbox' => 'INBOX']);
        }
    } catch (Throwable $e) {
        // keep default
    }
    header('Location: ' . $target);
    exit;
}

// Détails pour admin
$logTail = '';
$logFile = INSTALL_PATH . 'logs/errors.log';
if (is_readable($logFile)) {
    $lines = @file($logFile);
    if (is_array($lines) && $lines) {
        $logTail = implode('', array_slice($lines, -8));
    }
}

http_response_code(403);
echo "Connexion Roundcube impossible pour {$user}.\n\n";
echo "Causes fréquentes :\n";
echo "  1) Mot de passe boîte incorrect / non synchronisé Dovecot\n";
echo "  2) Dovecot arrêté ou maps dovecot-users illisibles (groupe vmail)\n";
echo "  3) Maildir inaccessible pour l'utilisateur vmail\n\n";
echo "Réparez sur le serveur :\n";
echo "  sudo bash /opt/vzone-src/scripts/repair-mail-auth.sh\n";
echo "  doveadm auth test '{$user}' 'VOTRE_MOT_DE_PASSE'\n";
echo "  Puis réinitialisez le MDP de la boîte dans le panel et rouvrez le webmail.\n\n";
if ($errors) {
    echo "Essais IMAP :\n- " . implode("\n- ", $errors) . "\n\n";
}
if ($logTail !== '') {
    echo "--- logs/errors.log ---\n{$logTail}\n";
}
exit;
