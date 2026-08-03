<?php
/**
 * Configuration phpMyAdmin — V-zone Panel (auth signon style cPanel).
 */
declare(strict_types=1);

$cfg['blowfish_secret'] = '__BLOWFISH__';

$cfg['TempDir'] = __DIR__ . '/tmp';

$i = 0;
$i++;
$cfg['Servers'][$i]['auth_type'] = 'signon';
$cfg['Servers'][$i]['host'] = 'localhost';
$cfg['Servers'][$i]['compress'] = false;
$cfg['Servers'][$i]['AllowNoPassword'] = false;
$cfg['Servers'][$i]['port'] = '3306';
$cfg['Servers'][$i]['SignonSession'] = 'VzonePmaSignon';
$cfg['Servers'][$i]['SignonURL'] = 'vzone-signon.php';
$cfg['Servers'][$i]['LogoutURL'] = 'vzone-signon.php?logout=1';

$cfg['UploadDir'] = '';
$cfg['SaveDir'] = '';
$cfg['DefaultLang'] = 'fr';
$cfg['CheckConfigurationPermissions'] = false;
$cfg['AllowArbitraryServer'] = false;
$cfg['LoginCookieValidity'] = 3600;
