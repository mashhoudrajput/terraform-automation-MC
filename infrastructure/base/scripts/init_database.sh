#!/bin/bash
set -e

LOG_FILE="/var/log/db-init-${cluster_uuid}.log"
exec > >(tee -a $LOG_FILE) 2>&1

echo "Database Initialization Started: $(date)"
echo "Is Sub-Hospital: ${is_sub_hospital}"

if ! command -v mysql &> /dev/null; then
    echo "Installing MySQL client..."
    apt-get update -qq
    DEBIAN_FRONTEND=noninteractive apt-get install -y -qq default-mysql-client google-cloud-sdk
fi

mkdir -p /tmp/sql/${cluster_uuid}

if [ "${is_sub_hospital}" = "true" ]; then
    echo "Sub-hospital mode: Copying sn_tables.sql and sub_network_views.sql"
    gsutil -q cp gs://${bucket_name}/database-init/${cluster_uuid}/sn_tables.sql /tmp/sql/${cluster_uuid}/ || true
    gsutil -q cp gs://${bucket_name}/database-init/${cluster_uuid}/sub_network_views.sql /tmp/sql/${cluster_uuid}/ || true
    if [ ! -f /tmp/sql/${cluster_uuid}/sn_tables.sql ]; then
        echo "ERROR: Failed to copy sn_tables.sql"
        exit 1
    fi
else
    echo "Main hospital mode: Copying ClusterDB.sql and sn_tables.sql"
    gsutil -q cp gs://${bucket_name}/database-init/${cluster_uuid}/ClusterDB.sql /tmp/sql/${cluster_uuid}/ || true
    gsutil -q cp gs://${bucket_name}/database-init/${cluster_uuid}/sn_tables.sql /tmp/sql/${cluster_uuid}/ || true
    if [ ! -f /tmp/sql/${cluster_uuid}/ClusterDB.sql ]; then
        echo "ERROR: Failed to copy ClusterDB.sql"
        exit 1
    fi
    if [ ! -f /tmp/sql/${cluster_uuid}/sn_tables.sql ]; then
        echo "ERROR: Failed to copy sn_tables.sql"
        exit 1
    fi
fi

echo "Waiting for database connection to be ready..."
for i in {1..12}; do
  sleep 5
  if mysql -h $${DB_HOST} -u $${DB_USER} -p'$${DB_PASSWORD}' -e "SELECT 1;" > /dev/null 2>&1; then
    echo "Database connection ready"
    break
  fi
  echo "Waiting for database... ($i/12)"
done

if [ "${is_sub_hospital}" = "true" ] && [ -z "${db_password}" ]; then
    echo "Sub-hospital: Getting password from parent secret"
    if [ -n "${parent_uuid}" ]; then
        PARENT_UUID_VAR="${parent_uuid}"
    else
        PARENT_UUID_VAR=$$(echo "${parent_instance_name}" | sed 's/mc-cluster-//' | tr '-' '_')
    fi
    PARENT_SECRET="$${PARENT_UUID_VAR}_DATABASE_URI"
    echo "Looking for parent secret: $${PARENT_SECRET}"
    CONNECTION_URI=$$(gcloud secrets versions access latest --secret="$${PARENT_SECRET}" --project="${project_id}" 2>/dev/null || echo "")
    if [ -z "$${CONNECTION_URI}" ]; then
        echo "Failed to get parent connection URI from secret: $${PARENT_SECRET}"
        exit 1
    fi
    DB_PASSWORD=$$(echo "$${CONNECTION_URI}" | sed -n 's|mysql://[^:]*:\([^@]*\)@.*|\1|p')
    DB_USER=$$(echo "$${CONNECTION_URI}" | sed -n 's|mysql://\([^:]*\):.*|\1|p')
    DB_HOST=$$(echo "$${CONNECTION_URI}" | sed -n 's|mysql://[^@]*@\([^:]*\):.*|\1|p')
    DB_PORT=$$(echo "$${CONNECTION_URI}" | sed -n 's|mysql://[^@]*@[^:]*:\([^/]*\)/.*|\1|p')
    echo "Using parent credentials from secret: $${PARENT_SECRET}"
else
    DB_PASSWORD="${db_password}"
    DB_USER="${db_user}"
    DB_HOST="${db_host}"
    DB_PORT="3306"
fi

mysql -h $${DB_HOST} -u $${DB_USER} -p'$${DB_PASSWORD}' -D ${db_name} -e "SELECT 1;" > /dev/null 2>&1
if [ $? -ne 0 ]; then
    echo "Database connection failed"
    exit 1
fi

if [ "${is_sub_hospital}" != "true" ]; then
    echo "Running ClusterDB.sql..."
    if [ -f /tmp/sql/${cluster_uuid}/ClusterDB.sql ]; then
        mysql -h $${DB_HOST} -u $${DB_USER} -p'$${DB_PASSWORD}' -D ${db_name} < /tmp/sql/${cluster_uuid}/ClusterDB.sql
        if [ $? -ne 0 ]; then
            echo "ERROR: Failed to execute ClusterDB.sql"
            exit 1
        fi
        echo "ClusterDB.sql executed successfully"
    else
        echo "ERROR: ClusterDB.sql not found"
        exit 1
    fi
fi

echo "Running sn_tables.sql..."
if [ -f /tmp/sql/${cluster_uuid}/sn_tables.sql ]; then
    mysql -h $${DB_HOST} -u $${DB_USER} -p'$${DB_PASSWORD}' -D ${db_name} < /tmp/sql/${cluster_uuid}/sn_tables.sql
    if [ $? -ne 0 ]; then
        echo "ERROR: Failed to execute sn_tables.sql"
        exit 1
    fi
    echo "sn_tables.sql executed successfully"
else
    echo "ERROR: sn_tables.sql not found"
    exit 1
fi

if [ "${is_sub_hospital}" = "true" ]; then
    echo "Running sub_network_views.sql..."
    if [ -f /tmp/sql/${cluster_uuid}/sub_network_views.sql ]; then
        mysql -h $${DB_HOST} -u $${DB_USER} -p'$${DB_PASSWORD}' -D ${db_name} < /tmp/sql/${cluster_uuid}/sub_network_views.sql
        if [ $? -ne 0 ]; then
            echo "ERROR: Failed to execute sub_network_views.sql"
            exit 1
        fi
        echo "sub_network_views.sql executed successfully"
    else
        echo "WARNING: sub_network_views.sql not found (optional for sub-hospitals)"
    fi
fi

TABLE_COUNT=$$(mysql -h $${DB_HOST} -u $${DB_USER} -p'$${DB_PASSWORD}' -D ${db_name} -e "SHOW TABLES;" | wc -l)
echo "Tables created: $((TABLE_COUNT - 1))"

echo "SUCCESS" > /tmp/db-init-${cluster_uuid}-complete
gsutil -q cp /tmp/db-init-${cluster_uuid}-complete gs://${bucket_name}/database-init/${cluster_uuid}/ || true

echo "Database Initialization Completed: $(date)"
