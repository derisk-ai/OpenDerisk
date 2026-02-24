#!/bin/sh
set -e

# ============================================================
# OpenDerisk Backend Entrypoint
# ============================================================

echo "=============================================="
echo "  OpenDerisk Backend Server Starting..."
echo "=============================================="

# Default config file
CONFIG_FILE="${DERISK_CONFIG_FILE:-configs/derisk-docker.toml}"

echo "  Config: ${CONFIG_FILE}"
echo "  Python: $(python --version)"
echo "=============================================="

# Run database migrations if using MySQL
if [ "${DB_TYPE}" = "mysql" ]; then
    echo "Waiting for MySQL to be ready..."
    max_retries=30
    retry_count=0
    while ! python -c "
import pymysql
pymysql.connect(
    host='${LOCAL_DB_HOST:-db}',
    port=${LOCAL_DB_PORT:-3306},
    user='${LOCAL_DB_USER:-root}',
    password='${LOCAL_DB_PASSWORD:-aa123456}',
    database='${LOCAL_DB_NAME:-derisk}'
)
print('MySQL connection successful')
" 2>/dev/null; do
        retry_count=$((retry_count + 1))
        if [ $retry_count -ge $max_retries ]; then
            echo "ERROR: MySQL is not available after ${max_retries} retries. Exiting."
            exit 1
        fi
        echo "  Waiting for MySQL... (${retry_count}/${max_retries})"
        sleep 2
    done
    echo "MySQL is ready!"
fi

# Start the backend server
echo "Starting OpenDerisk server..."
exec python packages/derisk-app/src/derisk_app/derisk_server.py \
    --config "${CONFIG_FILE}"
