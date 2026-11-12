<?php
// Synthetic local credentials only. No production config is mounted.
define('DB_NAME', 'audit3');
define('DB_USER', 'audit3');
define('DB_PASSWORD', 'synthetic-local-only');
define('DB_HOST', 'db:3306');
define('DB_CHARSET', 'utf8mb4');
define('DB_COLLATE', '');
$table_prefix = 'audit3_';
define('WP_DEBUG', true);
define('WP_DEBUG_DISPLAY', false);
define('DISALLOW_FILE_EDIT', true);
define('DISALLOW_FILE_MODS', true);
define('AUTOMATIC_UPDATER_DISABLED', true);
define('WP_HTTP_BLOCK_EXTERNAL', true);
define('WP_ACCESSIBLE_HOSTS', 'wordpress,services');
define('WP_HOME', 'http://wordpress:8080');
define('WP_SITEURL', 'http://wordpress:8080');
define('AUTH_KEY', 'synthetic-local-audit3-auth');
define('SECURE_AUTH_KEY', 'synthetic-local-audit3-secure');
define('LOGGED_IN_KEY', 'synthetic-local-audit3-login');
define('NONCE_KEY', 'synthetic-local-audit3-nonce');
define('AUTH_SALT', 'synthetic-local-audit3-auth-salt');
define('SECURE_AUTH_SALT', 'synthetic-local-audit3-secure-salt');
define('LOGGED_IN_SALT', 'synthetic-local-audit3-login-salt');
define('NONCE_SALT', 'synthetic-local-audit3-nonce-salt');
if (!defined('ABSPATH')) { define('ABSPATH', __DIR__ . '/'); }
require_once ABSPATH . 'wp-settings.php';
