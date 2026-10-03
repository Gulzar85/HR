#!/bin/sh
# Draft: nightly PostgreSQL backup. Requires DATABASE_URL.
pg_dump "$DATABASE_URL" -Fc -f "/var/backups/ems/ems-$(date +%F).dump"
