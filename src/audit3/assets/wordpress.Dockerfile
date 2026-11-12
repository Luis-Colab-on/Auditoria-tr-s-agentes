# Acquisition only: build explicitly, with reviewed versions/digests, before tests.
ARG WP_IMAGE=wordpress:6.7.2-php8.3-apache
ARG CLI_IMAGE=wordpress:cli-2.11.0-php8.3
FROM ${CLI_IMAGE} AS cli
FROM ${WP_IMAGE} AS wordpress
FROM php:8.3.17-cli-bookworm
RUN docker-php-ext-install mysqli
COPY --from=wordpress /usr/src/wordpress /usr/src/wordpress
COPY --from=cli /usr/local/bin/wp /usr/local/bin/wp
RUN mkdir -p /opt/audit3-plugins && chmod 755 /opt/audit3-plugins
# Optional, reviewed WooCommerce/plugins may be copied to /opt/audit3-plugins
# in an operator-owned derived image. No remote installation at test time.
USER 1000:1000
