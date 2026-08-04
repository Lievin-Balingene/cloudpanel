<?php
/**
 * Configuration Roundcube — V-zone Panel (webmail /webmail/).
 */
$config = [];

$config['db_dsnw'] = '__DB_DSN__';
// Doit rester vide : SQL/mysql.initial.sql crée session, users, etc. sans préfixe.
$config['db_prefix'] = '';

// IMAP / SMTP locaux (Dovecot + Postfix)
// Plain IMAP local : évite ssl://*:143 (wrong version number)
$config['imap_host'] = '127.0.0.1:143';
$config['imap_auth_type'] = 'LOGIN';
$config['smtp_host'] = 'tls://127.0.0.1:587';
$config['smtp_user'] = '%u';
$config['smtp_pass'] = '%p';

$config['support_url'] = '';
$config['product_name'] = 'V-zone Webmail';
$config['des_key'] = '__DES_KEY__';

$config['plugins'] = [
    'archive',
    'zipdownload',
    'markasjunk',
    'newmail_notifier',
];

$config['language'] = 'fr_FR';
$config['skin'] = 'elastic';
$config['enable_installer'] = false;
$config['auto_create_user'] = true;
$config['login_autocomplete'] = 2;
$config['log_driver'] = 'file';
$config['temp_dir'] = '__TEMP_DIR__';
$config['mime_types'] = null;

// Installé sous /webmail/
$config['request_path'] = '/webmail/';

// Certificats snakeoil / auto-signés en local
$config['imap_conn_options'] = [
    'ssl' => [
        'verify_peer'       => false,
        'verify_peer_name'  => false,
        'allow_self_signed' => true,
    ],
];
$config['smtp_conn_options'] = [
    'ssl' => [
        'verify_peer'       => false,
        'verify_peer_name'  => false,
        'allow_self_signed' => true,
    ],
];

$config['username_domain'] = '';
$config['mail_domain'] = '';
$config['create_default_folders'] = true;
$config['protect_default_folders'] = true;
$config['drafts_mbox'] = 'Drafts';
$config['junk_mbox'] = 'Junk';
$config['sent_mbox'] = 'Sent';
$config['trash_mbox'] = 'Trash';
$config['show_images'] = 0;
$config['check_all_folders'] = false;
$config['refresh_interval'] = 60;
$config['session_lifetime'] = 30;
$config['ip_check'] = false;
$config['cipher_method'] = 'AES-256-CBC';
