# Use the official WordPress image as the base
FROM wordpress:6.8.1-apache

# Update apt-get repositories
RUN apt update && apt install wget -y \
    && wget -O- https://getcomposer.org/installer | php -- --install-dir=/usr/local/bin --filename=composer


# Installs pdo_mysql so the Prime Mover plugin can be used.
# See more about installing PHP extensions here:
# https://github.com/docker-library/docs/blob/master/php/README.md#how-to-install-more-php-extensions
RUN docker-php-ext-install pdo_mysql

# Set the working directory to the main WordPress directory.
# This is where your composer.json should be if you're managing
# project-level dependencies.
WORKDIR /var/www/html

# Create a minimal composer.json file if it doesn't exist.
# This is a good practice to ensure Composer has a file to work with,
# even if you haven't explicitly created one for WordPress yet.
# You can replace the content below with your actual composer.json if you have one.
COPY composer.json composer.lock ./

# Install the firebase/php-jwt library using Composer.
# --no-dev: Skips installing development-specific dependencies, reducing image size.
# --optimize-autoloader: Optimizes the Composer autoloader for better performance.
RUN composer require firebase/php-jwt --optimize-autoloader


# This creates a docker development environment.
RUN cp /usr/local/etc/php/php.ini-development /usr/local/etc/php/php.ini

# Uncomment below and comment out dev environment in order to build a production environment
# RUN cp /usr/local/etc/php/php.ini-production /usr/local/etc/php/php.ini

# Keeps the host user and www-data as the same uid so Docker doesn't see
# a different number and complain.
# This ensures file permissions are consistent between the host and container.
RUN groupmod -g 1000 www-data \
    && usermod -u 1000 www-data \
    && usermod -g 1000 www-data \
    && chown -R www-data:www-data /var/www \
    && chmod g+s /var/www