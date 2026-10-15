# The tpch-loader image: generates a real TPC-H dataset (DuckDB's own tpch extension, which
# implements the actual dbgen row-generation/skew algorithm -- not a hand-rolled synthetic
# generator) and loads it into whichever LINEITEM object store and dimension-table database this
# add-on is pointed at. Runs once per `docker compose up` and exits; see generate_and_load.py's
# own module docstring for the idempotency check that makes re-running it a safe no-op.
#
# DuckDB, not the C `dbgen` binary: TPC's own dbgen source isn't freely redistributable without
# accepting TPC's license terms interactively, which has no clean place in an unattended Docker
# build. DuckDB's tpch extension (Apache-2.0, ships via `pip install duckdb`) implements the same
# generator and is the generator real query engines (DuckDB itself, and widely elsewhere) already
# use for TPC-H benchmarking -- real TPC-H row shapes/skew, no license friction.
FROM python:3.12-slim

WORKDIR /loader
RUN pip install --no-cache-dir duckdb==1.1.3 psycopg2-binary==2.9.10 boto3==1.35.68 azure-storage-blob==12.24.0

COPY generate_and_load.py .

ENTRYPOINT ["python", "generate_and_load.py"]
