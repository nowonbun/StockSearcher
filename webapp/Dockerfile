FROM composer:2 AS vendor
WORKDIR /app/webapp
COPY webapp/composer.json ./
RUN composer install --no-dev --prefer-dist --no-interaction --no-progress

FROM php:8.3-apache
WORKDIR /app

RUN apt-get update \
    && docker-php-ext-install pdo pdo_mysql \
    && rm -rf /var/lib/apt/lists/* \
    && a2enmod rewrite

COPY . /app
COPY --from=vendor /app/webapp/vendor /app/webapp/vendor
RUN mkdir -p /app/webapp/templates_c /app/webapp/cache /app/webapp/config \
    && chown -R www-data:www-data /app/webapp/templates_c /app/webapp/cache

COPY webapp/apache-webapp.conf /etc/apache2/conf-enabled/webapp.conf

ENV APACHE_DOCUMENT_ROOT=/app/webapp/public
RUN sed -ri -e 's!/var/www/html!${APACHE_DOCUMENT_ROOT}!g' /etc/apache2/sites-available/*.conf \
    && sed -ri -e 's!/var/www/!/app/webapp/!g' /etc/apache2/apache2.conf /etc/apache2/conf-available/*.conf

EXPOSE 80
