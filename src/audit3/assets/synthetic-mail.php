<?php
// WordPress derives wordpress@wordpress from the single-label synthetic host.
// PHPMailer rejects that before phpmailer_init; set a valid reserved From first.
add_filter('wp_mail_from', static function ($from) {
    return 'wordpress@audit3.example.invalid';
});
// SMTP capture is local only; network isolation also blocks raw socket bypasses.
add_action('phpmailer_init', function ($mail) {
    $mail->isSMTP();
    $mail->Host = 'services';
    $mail->Port = 1025;
    $mail->SMTPAuth = false;
    $mail->SMTPAutoTLS = false;
});
