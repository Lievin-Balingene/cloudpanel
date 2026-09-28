<?php
/**
 * SSO one-shot V-zone Panel → Roundcube.
 * Token JSON : { "user", "password", "imap_host", "exp" }
 *
 * Important : après login(), il faut set_auth_cookie() + regenerate_id
 * sinon Roundcube réaffiche le formulaire de connexion.
 */
declare(strict_types=1);

// Cookie de session limité au webmail (avant tout démarrage de session)
ini_set('session.cookie_path', '/webmail/');
ini_set('session.cookie_samesite', 'Lax');
ini_set('session.use_strict_mode', '1');

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
    exit(
        "Token invalide ou manquant.\n" .
        "Rouvrez le webmail depuis le bouton du panel.\n"
    );
}

$path = rtrim($ssoDir, '/') . '/' . $token . '.json';
$consumed = $path . '.used';

if (!is_file($path) || !@rename($path, $consumed)) {
    header('Content-Type: text/plain; charset=utf-8');
    http_response_code(403);
    exit(
        "Session expirée ou token déjà utilisé.\n" .
        "Rouvrez le webmail depuis le panel (un seul clic).\n" .
        "SSO dir: {$ssoDir}\n"
    );
}

if (!is_readable($consumed)) {
    @unlink($consumed);
    header('Content-Type: text/plain; charset=utf-8');
    http_response_code(403);
    exit("Token SSO illisible par PHP (droits).\n");
}

$raw = file_get_contents($consumed);
@unlink($consumed);
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
$tokenHost = trim((string)($data['imap_host'] ?? ''));

if ($user === '' || $pass === '') {
    header('Content-Type: text/plain; charset=utf-8');
    http_response_code(403);
    exit("Identifiants vides. Réinitialisez le mot de passe de la boîte dans le panel.\n");
}

define('INSTALL_PATH', rtrim(str_replace('\\', '/', __DIR__), '/') . '/');
require_once INSTALL_PATH . 'program/include/iniset.php';

/** @var rcmail $rcmail */
$rcmail = rcmail::get_instance();

try {
    if (method_exists($rcmail->session, 'set_cookie_path')) {
        $rcmail->session->set_cookie_path('/webmail/');
    }
} catch (Throwable $e) {
    // ignore
}

try {
    if (!empty($_SESSION['user_id']) || $rcmail->get_user_id()) {
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

// Hosts IMAP à essayer (ordre)
$hosts = [];
if ($tokenHost !== '') {
    $hosts[] = $tokenHost;
}
try {
    $cfgHost = $rcmail->config->get('imap_host');
    if (is_array($cfgHost)) {
        foreach ($cfgHost as $h) {
            if (is_string($h) && $h !== '') {
                $hosts[] = $h;
            }
        }
    } elseif (is_string($cfgHost) && $cfgHost !== '') {
        $hosts[] = $cfgHost;
    }
} catch (Throwable $e) {
    // ignore
}
$hosts = array_values(array_unique(array_merge($hosts, [
    '127.0.0.1:143',
    'localhost:143',
    '127.0.0.1',
    'localhost',
])));

$ok = false;
$errors = [];
$usedHost = '';

foreach ($hosts as $host) {
    try {
        $auth = [
            'host' => $host,
            'user' => $user,
            'pass' => $pass,
            'cookiecheck' => false,
            'valid' => false,
            'abort' => false,
        ];
        try {
            $auth = $rcmail->plugins->exec_hook('authenticate', $auth);
        } catch (Throwable $e) {
            // pas de plugins / hook KO
        }
        if (!empty($auth['abort'])) {
            $errors[] = "{$host}: authenticate abort";
            continue;
        }

        $ok = (bool)$rcmail->login(
            (string)$auth['user'],
            (string)$auth['pass'],
            $auth['host'] ?? $host,
            false
        );
        if ($ok) {
            $usedHost = is_string($auth['host'] ?? null) ? (string)$auth['host'] : (string)$host;
            break;
        }
        $errors[] = "{$host}: login=false";
    } catch (Throwable $e) {
        $errors[] = "{$host}: " . $e->getMessage();
        $ok = false;
    }
}

if ($ok) {
    try {
        // Critique : sans auth cookie, le redirect tombe sur l'écran login
        if (method_exists($rcmail->session, 'remove')) {
            $rcmail->session->remove('temp');
            $rcmail->session->remove('temp_start_time');
        }
        if (method_exists($rcmail->session, 'regenerate_id')) {
            $rcmail->session->regenerate_id(false);
        }
        if (method_exists($rcmail->session, 'set_auth_cookie')) {
            $rcmail->session->set_auth_cookie();
        }
    } catch (Throwable $e) {
        $errors[] = 'session: ' . $e->getMessage();
    }

    try {
        if (method_exists($rcmail->session, 'write')) {
            $rcmail->session->write();
        } elseif (method_exists($rcmail->session, 'write_close')) {
            $rcmail->session->write_close();
        } else {
            session_write_close();
        }
    } catch (Throwable $e) {
        @session_write_close();
    }

    $base = '/webmail/';
    try {
        $rp = (string)$rcmail->config->get('request_path', '/webmail/');
        if ($rp !== '') {
            $base = rtrim($rp, '/') . '/';
        }
    } catch (Throwable $e) {
        // keep
    }

    // index.php explicite — évite les ambiguïtés alias nginx
    $target = $base . 'index.php?_task=mail&_mbox=INBOX';
    try {
        if (method_exists($rcmail, 'url')) {
            $u = (string)$rcmail->url(['_task' => 'mail', '_mbox' => 'INBOX']);
            if ($u !== '' && !preg_match('#vzone-sso\.php#i', $u)) {
                if (str_starts_with($u, 'http://') || str_starts_with($u, 'https://')) {
                    $target = $u;
                } elseif (str_starts_with($u, '/')) {
                    $target = $u;
                } else {
                    $target = $base . ltrim($u, './');
                }
            }
        }
    } catch (Throwable $e) {
        // keep $target
    }

    header('Cache-Control: no-store, no-cache, must-revalidate');
    header('Location: ' . $target, true, 303);
    exit;
}

header('Content-Type: text/plain; charset=utf-8');
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
echo "1) sudo bash /opt/vzone-src/scripts/repair-mail-auth.sh\n";
echo "2) Réinitialisez le mot de passe de la boîte dans le panel\n";
echo "3) Retestez Webmail (un clic)\n\n";
if ($errors) {
    echo "Essais IMAP :\n- " . implode("\n- ", $errors) . "\n\n";
}
if ($logTail !== '') {
    echo "--- logs/errors.log ---\n{$logTail}\n";
}
exit;
