<?php
/**
 * Plugin Name: Audit3 Synthetic Plugin
 * Version: 0.0.1
 */
add_action('rest_api_init', function () {
    register_rest_route('audit3/v1', '/ping', [
        'methods' => 'GET',
        'permission_callback' => '__return_true',
        'callback' => function () { return ['synthetic' => true, 'ok' => true]; },
    ]);
});
add_action('wp_ajax_audit3_echo', function () {
    check_ajax_referer('audit3_echo');
    if (!current_user_can('manage_options')) {
        wp_send_json_error(['reason' => 'forbidden'], 403);
    }
    wp_send_json_success(['synthetic' => true]);
});
