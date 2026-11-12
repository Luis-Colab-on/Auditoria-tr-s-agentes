#!/bin/sh
# Trusted bootstrap. Executed only inside the isolated container, never on the host.
set -eu
mkdir -p /work/wordpress
cp -R /usr/src/wordpress/. /work/wordpress/
cp /opt/audit3/wp-config.php /work/wordpress/wp-config.php
mkdir -p /work/wordpress/wp-content/mu-plugins
cp /opt/audit3/synthetic-mail.php /work/wordpress/wp-content/mu-plugins/audit3-mail.php
if [ -d /opt/audit3-plugins ]; then
    cp -R /opt/audit3-plugins/. /work/wordpress/wp-content/plugins/
fi
ln -s /source "/work/wordpress/wp-content/plugins/$AUDIT3_PLUGIN_SLUG"
attempt=0
until wp --path=/work/wordpress core install --url=http://wordpress:8080 --title=Synthetic --admin_user=audit3 --admin_password=synthetic-only --admin_email=admin@example.invalid --skip-email; do
    attempt=$((attempt + 1))
    [ "$attempt" -lt 25 ] || exit 1
    sleep 1
done
if wp --path=/work/wordpress plugin is-installed woocommerce; then
    wp --path=/work/wordpress plugin activate woocommerce
fi
wp --path=/work/wordpress plugin activate "$AUDIT3_PLUGIN_SLUG"
touch /work/ready
exec php -S 0.0.0.0:8080 -t /work/wordpress
