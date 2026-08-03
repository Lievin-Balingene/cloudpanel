<?php
/**
 * SSO one-shot depuis V-zone Panel → session phpMyAdmin.
 * Token écrit par Django dans __SSO_DIR__/<token>.json
 */
declare(strict_types=1);

$ssoDir = '__SSO_DIR__';
$token = preg_replace('/[^a-f0-9]/', '', (string)($_GET['t'] ?? ''));
if ($token === '' || strlen($token) < 32) {
    http_response_code(400);
    exit('Token invalide.');
}

$path = rtrim($ssoDir, '/') . '/' . $token . '.json';
if (!is_file($path)) {
    http_response_code(403);
    exit('Session expirée ou token inconnu. Rouvrez phpMyAdmin depuis le panel.');
}

$raw = file_get_contents($path);
@unlink($path);
$data = json_decode((string)$raw, true);
if (!is_array($data) || empty($data['user']) || !isset($data['password'])) {
    http_response_code(403);
    exit('Token corrompu.');
}
if (!empty($data['exp']) && time() > (int)$data['exp']) {
    http_response_code(403);
    exit('Token expiré.');
}

session_name('VzonePmaSignon');
session_start();
$_SESSION['PMA_single_signon_user'] = (string)$data['user'];
$_SESSION['PMA_single_signon_password'] = (string)$data['password'];
$_SESSION['PMA_single_signon_host'] = (string)($data['host'] ?? 'localhost');

header('Location: index.php');
exit;
