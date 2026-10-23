#!/bin/sh
# Konteyner açılışında veritabanı şemasını ve önbellek tablosunu hazırlar.
set -e
python manage.py migrate --noinput
python manage.py createcachetable
exec "$@"
