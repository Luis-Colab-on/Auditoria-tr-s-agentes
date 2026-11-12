<?php
require '/work/wordpress/wp-load.php';
function audit3_assert($condition, $label) {
    if (!$condition) {
        fwrite(STDERR, "ASSERTION_FAILED $label\n");
        exit(1);
    }
    echo "ASSERTION_PASSED $label\n";
}
audit3_assert(function_exists('audit3_stock_reserve'), 'plugin_loaded');
wp_set_current_user(0);
audit3_assert(rest_do_request('/audit3-stock/v1/inventory')->get_status() === 403, 'anonymous_denied');
$subscriber = wp_insert_user(['user_login' => 'stock_reader', 'user_pass' => 'synthetic-only', 'role' => 'subscriber']);
audit3_assert(!is_wp_error($subscriber), 'subscriber_created');
wp_set_current_user($subscriber);
audit3_assert(rest_do_request('/audit3-stock/v1/inventory')->get_status() === 403, 'subscriber_denied');
$admins = get_users(['role' => 'administrator', 'number' => 1]);
audit3_assert(count($admins) === 1, 'administrator_exists');
wp_set_current_user($admins[0]->ID);
audit3_assert(rest_do_request('/audit3-stock/v1/inventory')->get_status() === 200, 'administrator_allowed');
audit3_assert(is_wp_error(audit3_stock_reserve(10, -3)), 'negative_quantity_rejected');
audit3_assert(is_wp_error(audit3_stock_reserve(10, 11)), 'excess_quantity_rejected');
$actual = audit3_stock_reserve(10, 3);
audit3_assert($actual === 7, 'reservation expected=7 actual=' . var_export($actual, true));
