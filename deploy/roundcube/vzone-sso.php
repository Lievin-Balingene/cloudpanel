<?php
/**
 * SSO one-shot V-zone Panel → Roundcube (style cPanel webmail).
 * Token JSON écrit par Django dans __SSO_DIR__/<token>.json
 *
 * Payload attendu :
 *   { "user": "box@domaine.tld", "password": "...", "imap_host": "127.0.0.1", "exp": <unix> }
 */
declare(strict_types=1);

$ssoDir = '__SSO_DIR__';
$token = preg_replace('/[^a-f0-9]/', '', (string)($_GET['t'] ?? ''));
if ($token === '' || strlen($token) < 32) {
    http_response_code(400);
    header('Content-Type: text/plain; charset=utf-8');
    exit('Token invalide.');
}

$path = rtrim($ssoDir, '/') . '/' . $token . '.json';
if (!is_file($path)) {
    http_response_code(403);
    header('Content-Type: text/plain; charset=utf-8');
    exit('Session expirée ou token inconnu. Rouvrez le webmail depuis le panel.');
}

$raw = file_get_contents($path);
@unlink($path);
$data = json_decode((string)$raw, true);
if (!is_array($data) || empty($data['user']) || !isset($data['password'])) {
    http_response_code(403);
    header('Content-Type: text/plain; charset=utf-8');
    exit('Token corrompu.');
}
if (!empty($data['exp']) && time() > (int)$data['exp']) {
    http_response_code(403);
    header('Content-Type: text/plain; charset=utf-8');
    exit('Token expiré.');
}

$user = (string)$data['user'];
$pass = (string)$data['password'];
$host = (string)($data['imap_host'] ?? '127.0.0.1');

define('INSTALL_PATH', rtrim(str_replace('\\', '/', __DIR__), '/') . '/');

// Bootstrap Roundcube
require_once INSTALL_PATH . 'program/include/iniset.php';

/** @var rcmail $rcmail */
$rcmail = rcmail::get_instance();

// Nettoyer une éventuelle session précédente
if (!empty($_SESSION['user_id'])) {
    try {
        $rcmail->logout_actions();
        $rcmail->kill_session();
        $rcmail->session->remove();
    } catch (Throwable $e) {
        // ignore
    }
    // Redémarrer une session propre
    $rcmail->session->start();
}

$ok = false;
try {
    $ok = (bool)$rcmail->login($user, $pass, $host, false);
} catch (Throwable $e) {
    $ok = false;
}

if ($ok) {
    // Persiste la session avant redirect
    if (method_exists($rcmail->session, 'write')) {
        $rcmail->session->write();
    }
    $target = './?_task=mail&_mbox=INBOX';
    if (method_exists($rcmail, 'url')) {
        try {
            $target = $rcmail->url(['_task' => 'mail', '_mbox' => 'INBOX']);
        } catch (Throwable $e) {
            $target = './?_task=mail&_mbox=INBOX';
        }
    }
    header('Location: ' . $target);
    exit;
}

http_response_code(403);
header('Content-Type: text/plain; charset=utf-8');
echo "Connexion Roundcube impossible pour {$user}.\n";
echo "Vérifiez que Dovecot tourne, que la boîte existe dans les maps, et que le mot de passe est correct.\n";
echo "Astuce : réinitialisez le mot de passe de la boîte dans le panel, puis réessayez.\n";
exit;
