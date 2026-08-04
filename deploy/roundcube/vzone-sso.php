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

/**
 * Normalise un host IMAP Roundcube.
 * Interdit ssl://*:143 (plain IMAP + SSL wrap → wrong version number).
 */
$normalizeHost = static function (?string $h): ?string {
    if ($h === null) {
        return null;
    }
    $h = trim($h);
    if ($h === '') {
        return null;
    }
    // Bare host / host:port → IMAPS 993 (snakeoil + verify_peer=false)
    if (!preg_match('#^(ssl|tls|imaps?)://#i', $h)) {
        if (preg_match('#:143$#', $h) || !str_contains($h, ':')) {
            $host = preg_replace('#:\\d+$#', '', $h) ?: '127.0.0.1';
            return 'ssl://' . $host . ':993';
        }
        return $h;
    }
    // ssl://host:143 → corriger vers 993
    if (preg_match('#^ssl://([^:/]+)(?::143)?$#i', $h, $m)) {
        return 'ssl://' . $m[1] . ':993';
    }
    if (preg_match('#^ssl://[^:]+:143$#i', $h)) {
        return preg_replace('#:143$#', ':993', $h);
    }
    return $h;
};

$hosts = [];
foreach ([
    $normalizeHost($hostHint),
    'ssl://127.0.0.1:993',
    '127.0.0.1:143', // plain LOGIN (disable_plaintext_auth=no)
    null,
] as $h) {
    if ($h === null) {
        if (!in_array(null, $hosts, true)) {
            $hosts[] = null;
        }
        continue;
    }
    if ($h !== '' && !in_array($h, $hosts, true)) {
        $hosts[] = $h;
    }
}

$ok = false;
$errors = [];
foreach ($hosts as $host) {
    try {
        $ok = (bool)$rcmail->login($user, $pass, $host, false);
        if ($ok) {
            break;
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
echo "Cause typique : Dovecot UNAVAILABLE (maps illisibles).\n";
echo "Réparez : sudo bash /opt/vzone-src/scripts/repair-mail-auth.sh\n";
echo "Test   : doveadm auth test '{$user}' 'VOTRE_MOT_DE_PASSE'\n\n";
if ($errors) {
    echo "Essais IMAP :\n- " . implode("\n- ", $errors) . "\n\n";
}
if ($logTail !== '') {
    echo "--- logs/errors.log ---\n{$logTail}\n";
}
exit;
