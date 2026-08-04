<?php
/**
 * SSO one-shot V-zone Panel → Roundcube.
 * Token JSON : { "user", "password", "imap_host", "exp" }
 */
declare(strict_types=1);

/**
 * Récupère le token même si $_GET est vide (QUERY_STRING nginx/alias).
 */
function vzone_sso_token(): string
{
    $raw = (string)($_GET['t'] ?? '');
    if ($raw === '' && !empty($_SERVER['QUERY_STRING'])) {
        parse_str((string)$_SERVER['QUERY_STRING'], $qs);
        $raw = (string)($qs['t'] ?? '');
    }
    if ($raw === '' && !empty($_SERVER['REQUEST_URI'])) {
        if (preg_match('/[?&]t=([a-fA-F0-9]+)/', (string)$_SERVER['REQUEST_URI'], $m)) {
            $raw = $m[1];
        }
    }
    return preg_replace('/[^a-f0-9]/i', '', $raw) ?? '';
}

$ssoDir = '__SSO_DIR__';
$token = vzone_sso_token();
if ($token === '' || strlen($token) < 32) {
    header('Content-Type: text/plain; charset=utf-8');
    http_response_code(400);
    $qs = (string)($_SERVER['QUERY_STRING'] ?? '');
    $uri = (string)($_SERVER['REQUEST_URI'] ?? '');
    exit(
        "Token invalide ou manquant.\n" .
        "Rouvrez le webmail depuis le bouton du panel (ne rechargez pas cette page).\n" .
        "Si ça continue: sudo bash /opt/vzone-src/scripts/repair-roundcube.sh\n" .
        "et sudo bash /opt/vzone-src/scripts/ensure-nginx.sh\n" .
        "debug: qs={$qs} uri={$uri}\n"
    );
}

$path = rtrim($ssoDir, '/') . '/' . $token . '.json';
if (!is_file($path) || !is_readable($path)) {
    header('Content-Type: text/plain; charset=utf-8');
    http_response_code(403);
    exit(
        "Session expirée ou token déjà utilisé.\n" .
        "Rouvrez le webmail depuis le panel (nouveau token, 90s).\n" .
        "SSO dir: {$ssoDir}\n"
    );
}

$raw = file_get_contents($path);
@unlink($path);
$data = json_decode((string)$raw, true);
if (!is_array($data) || empty($data['user']) || !array_key_exists('password', $data)) {
    header('Content-Type: text/plain; charset=utf-8');
    http_response_code(403);
    exit("Token corrompu.\n");
}
if (!empty($data['exp']) && time() > (int)$data['exp']) {
    header('Content-Type: text/plain; charset=utf-8');
    http_response_code(403);
    exit("Token expiré. Rouvrez le webmail depuis le panel.\n");
}

$user = trim((string)$data['user']);
$pass = (string)$data['password'];

if ($user === '' || $pass === '') {
    header('Content-Type: text/plain; charset=utf-8');
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

$hosts = ['127.0.0.1:143', null];

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
    try {
        if (method_exists($rcmail->session, 'write_close')) {
            $rcmail->session->write_close();
        } else {
            session_write_close();
        }
    } catch (Throwable $e) {
        @session_write_close();
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

header('Content-Type: text/plain; charset=utf-8');
$logTail = '';
$logFile = INSTALL_PATH . 'logs/errors.log';
if (is_readable($logFile)) {
    $lines = @file($logFile);
    if (is_array($lines) && $lines) {
        $logTail = implode('', array_slice($lines, -6));
    }
}

http_response_code(403);
echo "Connexion Roundcube impossible pour {$user}.\n\n";
echo "Réparez : sudo bash /opt/vzone-src/scripts/repair-mail-auth.sh\n\n";
if ($errors) {
    echo "Essais IMAP :\n- " . implode("\n- ", $errors) . "\n\n";
}
if ($logTail !== '') {
    echo "--- logs/errors.log ---\n{$logTail}\n";
}
exit;
