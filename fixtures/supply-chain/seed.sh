#!/bin/bash
# Seeds all four real databases in the supply-chain fixture. Run `docker compose up -d` first
# (or let this script do it), then run this. Idempotent -- safe to re-run.
set -euo pipefail
cd "$(dirname "$0")"

echo "starting containers (no-op if already up)..."
docker compose up -d

echo "waiting for all four databases to be ready..."
for i in $(seq 1 40); do
  ok_pg=$(docker exec sc-postgres pg_isready -U postgres 2>&1 | grep -c "accepting connections" || true)
  ok_my=$(docker exec sc-mysql mysqladmin ping -uroot -pomnigate 2>&1 | grep -c "mysqld is alive" || true)
  ok_or=$(docker logs sc-oracle 2>&1 | grep -c "DATABASE IS READY TO USE" || true)
  ok_ms=$(docker logs sc-mssql 2>&1 | grep -ic "Recovery is complete" || true)
  if [ "$ok_pg" = "1" ] && [ "$ok_my" = "1" ] && [ "$ok_or" -ge "1" ] && [ "$ok_ms" -ge "1" ]; then
    echo "all four ready"
    break
  fi
  sleep 5
done

echo "seeding suppliers (Postgres)..."
docker exec -i sc-postgres psql -U postgres -d suppliers < seed-postgres.sql

echo "seeding inventory (MySQL)..."
docker exec -i sc-mysql mysql -uroot -pomnigate inventory < seed-mysql.sql

echo "seeding procurement (Oracle) -- step 1: real non-system user..."
docker cp seed-oracle-1-user.sql sc-oracle:/tmp/seed-oracle-1-user.sql
docker exec sc-oracle sqlplus -s system/omnigate@//localhost:1521/freepdb1 @/tmp/seed-oracle-1-user.sql

echo "seeding procurement (Oracle) -- step 2: real data..."
docker cp seed-oracle-2-data.sql sc-oracle:/tmp/seed-oracle-2-data.sql
docker exec sc-oracle sqlplus -s procurement/omnigate@//localhost:1521/freepdb1 @/tmp/seed-oracle-2-data.sql

echo "seeding logistics (SQL Server) -- via a real mssql-tools container on the fixture's own network..."
docker run --rm --network supply-chain-fixture-net \
  -v "$(pwd)/seed-mssql.sql:/seed.sql" mcr.microsoft.com/mssql-tools \
  /opt/mssql-tools/bin/sqlcmd -S sc-mssql -U sa -P 'OmniGate!Strong1' -i /seed.sql

echo
echo "done. Four real databases seeded:"
echo "  suppliers   (Postgres)   127.0.0.1:15432/suppliers   user=postgres pass=omnigate"
echo "  inventory   (MySQL)      127.0.0.1:13306/inventory   user=root     pass=omnigate"
echo "  procurement (Oracle)     127.0.0.1:11521/freepdb1    user=procurement pass=omnigate"
echo "  logistics   (SQL Server) 127.0.0.1:11433/logistics   user=sa       pass=OmniGate!Strong1"
echo
echo "See README.md for the real OMNIGATE_BACKENDS/OMNIGATE_ROUTER_SCHEMA_RULES config."
