#!/bin/sh
set -e

echo "Waiting for database..."
while ! nc -z db 5432; do
  sleep 1
done
echo "Database is up!"

python manage.py migrate --noinput
python manage.py collectstatic --noinput

exec "$@"

