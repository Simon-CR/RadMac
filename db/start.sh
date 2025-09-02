#!/bin/bash
# Start MariaDB using the original entrypoint
# Don't try to run a health server - let Docker healthchecks handle this

exec docker-entrypoint.sh mysqld
