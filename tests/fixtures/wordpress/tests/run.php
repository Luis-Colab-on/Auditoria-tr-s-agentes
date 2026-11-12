<?php
require '/work/wordpress/wp-load.php';
$response = rest_do_request('/audit3/v1/ping');
if ($response->get_status() !== 200 || !$response->get_data()['synthetic']) {
    fwrite(STDERR, "synthetic REST assertion failed\n");
    exit(1);
}
echo "synthetic REST assertion passed\n";
