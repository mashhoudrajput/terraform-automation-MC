#!/bin/bash
set -e

LOG_FILE="/var/log/db-init-${cluster_uuid}.log"
exec > >(tee -a $LOG_FILE) 2>&1

echo "Database Initialization Started: $(date)"

if ! command -v mysql &> /dev/null; then
    echo "Installing MySQL client..."
    apt-get update -qq
    DEBIAN_FRONTEND=noninteractive apt-get install -y -qq default-mysql-client google-cloud-sdk
fi

mkdir -p /tmp/sql/${cluster_uuid}
gsutil -q cp gs://${bucket_name}/database-init/${cluster_uuid}/ClusterDB.sql /tmp/sql/${cluster_uuid}/
gsutil -q cp gs://${bucket_name}/database-init/${cluster_uuid}/sn_tables.sql /tmp/sql/${cluster_uuid}/

sleep 30

mysql -h ${db_host} -u ${db_user} -p'${db_password}' -D ${db_name} -e "SELECT 1;" > /dev/null 2>&1
if [ $? -ne 0 ]; then
    echo "Database connection failed"
    exit 1
fi

mysql -h ${db_host} -u ${db_user} -p'${db_password}' -D ${db_name} < /tmp/sql/${cluster_uuid}/ClusterDB.sql
mysql -h ${db_host} -u ${db_user} -p'${db_password}' -D ${db_name} < /tmp/sql/${cluster_uuid}/sn_tables.sql

TABLE_COUNT=$(mysql -h ${db_host} -u ${db_user} -p'${db_password}' -D ${db_name} -e "SHOW TABLES;" | wc -l)
echo "Tables created: $((TABLE_COUNT - 1))"

echo "SUCCESS" > /tmp/db-init-${cluster_uuid}-complete
gsutil -q cp /tmp/db-init-${cluster_uuid}-complete gs://${bucket_name}/database-init/${cluster_uuid}/

echo "Database Initialization Completed: $(date)"

