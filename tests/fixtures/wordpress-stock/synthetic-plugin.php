<?php
/**
 * Plugin Name: Audit3 Synthetic Stock
 * Version: 0.0.1
 */
require_once __DIR__ . '/inventory.php';

function audit3_stock_permission() {
    if (!current_user_can('manage_options')) {
        return new WP_Error('audit3_stock_forbidden', 'Inventory requires administration.', ['status' => 403]);
    }
    return true;
}

add_action('rest_api_init', function () {
    register_rest_route('audit3-stock/v1', '/inventory', [
        'methods' => 'GET',
        'permission_callback' => 'audit3_stock_permission',
        'callback' => function () { return ['synthetic' => true, 'stock' => 10]; },
    ]);
});
