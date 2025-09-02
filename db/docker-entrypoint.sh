#!/bin/bash
set -eo pipefail

# MariaDB Alpine Entrypoint Script
# Based on official MariaDB Docker entrypoint but adapted for Alpine

# usage: file_env VAR [DEFAULT]
#    ie: file_env 'XYZ_DB_PASSWORD' 'example'
# (will allow for "$XYZ_DB_PASSWORD_FILE" to fill in the value of
#  "$XYZ_DB_PASSWORD" from a file, especially for Docker's secrets feature)
file_env() {
	local var="$1"
	local fileVar="${var}_FILE"
	local def="${2:-}"
	if [ "${!var:-}" ] && [ "${!fileVar:-}" ]; then
		echo >&2 "error: both $var and $fileVar are set (but are exclusive)"
		exit 1
	fi
	local val="$def"
	if [ "${!var:-}" ]; then
		val="${!var}"
	elif [ "${!fileVar:-}" ]; then
		val="$(< "${!fileVar}")"
	fi
	export "$var"="$val"
	unset "$fileVar"
}

# Initialize MariaDB data directory if it doesn't exist
if [ ! -d "/var/lib/mysql/mysql" ]; then
	echo 'Initializing database...'
	
	file_env 'MARIADB_ROOT_PASSWORD'
	file_env 'MARIADB_DATABASE'
	file_env 'MARIADB_USER'
	file_env 'MARIADB_PASSWORD'

	# Initialize the database
	mysql_install_db --user=mysql --datadir=/var/lib/mysql

	# Start temporary server for setup
	mariadbd --user=mysql --datadir=/var/lib/mysql --skip-networking --socket=/tmp/mysql_init.sock &
	pid="$!"

	# Wait for server to start
	for i in {30..0}; do
		if echo 'SELECT 1' | mysql --protocol=socket -uroot -hlocalhost --socket=/tmp/mysql_init.sock &> /dev/null; then
			break
		fi
		echo 'MySQL init process in progress...'
		sleep 1
	done

	if [ "$i" = 0 ]; then
		echo >&2 'MySQL init process failed.'
		exit 1
	fi

	# Set root password
	if [ "$MARIADB_ROOT_PASSWORD" ]; then
		mysql --protocol=socket -uroot -hlocalhost --socket=/tmp/mysql_init.sock <<-EOSQL
			SET @@SESSION.SQL_LOG_BIN=0;
			DELETE FROM mysql.user WHERE user NOT IN ('mysql.sys', 'mysqlxsys', 'root') OR host NOT IN ('localhost');
			SET PASSWORD FOR 'root'@'localhost'=PASSWORD('${MARIADB_ROOT_PASSWORD}');
			GRANT ALL ON *.* TO 'root'@'%' IDENTIFIED BY '${MARIADB_ROOT_PASSWORD}' WITH GRANT OPTION;
			FLUSH PRIVILEGES;
		EOSQL
	fi

	# Create database
	if [ "$MARIADB_DATABASE" ]; then
		mysql --protocol=socket -uroot -hlocalhost --socket=/tmp/mysql_init.sock <<-EOSQL
			CREATE DATABASE IF NOT EXISTS \`$MARIADB_DATABASE\`;
		EOSQL
	fi

	# Create user
	if [ "$MARIADB_USER" ] && [ "$MARIADB_PASSWORD" ]; then
		mysql --protocol=socket -uroot -hlocalhost --socket=/tmp/mysql_init.sock <<-EOSQL
			CREATE USER '$MARIADB_USER'@'%' IDENTIFIED BY '$MARIADB_PASSWORD';
			GRANT ALL ON \`$MARIADB_DATABASE\`.* TO '$MARIADB_USER'@'%';
			FLUSH PRIVILEGES;
		EOSQL
	fi

	# Run initialization scripts
	for f in /docker-entrypoint-initdb.d/*; do
		case "$f" in
			*.sh)     echo "$0: running $f"; . "$f" ;;
			*.sql)    echo "$0: running $f"; mysql --protocol=socket -uroot -hlocalhost --socket=/tmp/mysql_init.sock < "$f"; echo ;;
			*.sql.gz) echo "$0: running $f"; gunzip -c "$f" | mysql --protocol=socket -uroot -hlocalhost --socket=/tmp/mysql_init.sock; echo ;;
			*)        echo "$0: ignoring $f" ;;
		esac
		echo
	done

	# Stop temporary server
	if ! kill -s TERM "$pid" || ! wait "$pid"; then
		echo >&2 'MySQL init process failed.'
		exit 1
	fi

	echo 'Database initialization complete'
fi

# Start MariaDB with the provided arguments
exec "$@"
