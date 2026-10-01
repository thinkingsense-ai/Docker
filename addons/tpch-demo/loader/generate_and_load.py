#!/usr/bin/env python3
"""Generates a real TPC-H dataset via DuckDB's own tpch extension (real dbgen row shapes/skew,
not a synthetic approximation) at TPCH_SCALE_FACTOR (1 == ~1GB total, matching dbgen's own
documented sizing), writes LINEITEM to Parquet and uploads it to whichever S3-compatible or Azure
Blob target this add-on is configured for, and loads the other seven TPC-H tables (customer,
orders, part, partsupp, supplier, nation, region) into a Postgres database -- the same two-source
split (LINEITEM in object storage, dimension tables in a relational database) this project's own
TPC-H benchmark work already uses.

Idempotent by design, not by accident: before generating anything, it checks whether the target
LINEITEM object and the target Postgres tables already have data, and exits immediately if both
are already populated -- so `docker compose up` on an already-loaded stack is a fast no-op, not a
silent 1GB regeneration on every restart. Pass TPCH_FORCE_RELOAD=true to override this and reload
anyway (e.g. after changing TPCH_SCALE_FACTOR).

Scope, disclosed rather than silently assumed: dimension tables are loaded into Postgres only in
this version -- the loader speaks plain psycopg2/COPY, which is Postgres-specific. Pointing
TPCH_DIM_JDBC_URL at a different relational database (MySQL, Oracle, SQL Server) will NOT work
without a real, separate loader path for that database's own bulk-load mechanism; this is real,
scoped-out follow-on work, not a silent limitation to discover only when it fails.
"""
import os
import sys
import io
import time
import duckdb
import psycopg2

# Real FK dependency order (region before nation, nation before supplier/customer, etc.) -- loading
# out of order trips a real foreign-key violation on the target Postgres (found live).
DIMENSION_TABLES = ["region", "nation", "part", "supplier", "partsupp", "customer", "orders"]


def env(name, default=None, required=False):
    value = os.environ.get(name, default)
    if required and not value:
        print(f"tpch-loader: missing required env var {name}", file=sys.stderr)
        sys.exit(1)
    return value


def log(msg):
    print(f"tpch-loader: {msg}", flush=True)


# ---------------------------------------------------------------------------------------------
# Idempotency check -- real, not a guess: looks at whether the target already has the expected
# row count for ONE dimension table (orders, the largest/cheapest-to-check non-lineitem table at
# this scale) and whether the lineitem object already exists at the target endpoint.
# ---------------------------------------------------------------------------------------------

def dimension_tables_loaded(dim_conn, expected_orders_rows):
    try:
        with dim_conn.cursor() as cur:
            cur.execute("SELECT to_regclass('public.orders')")
            if cur.fetchone()[0] is None:
                return False
            cur.execute("SELECT count(*) FROM orders")
            return cur.fetchone()[0] >= expected_orders_rows
    except Exception as e:  # noqa: BLE001 -- any failure here just means "not loaded yet"
        log(f"dimension-table check failed ({e}) -- treating as not loaded")
        return False


def already_loaded(con, dim_conn, expected_orders_rows):
    """S3-compatible-target idempotency check: real row count on the dimension side, real glob
    match against the configured lineitem URI (set into lineitem_probe_glob by
    configure_duckdb_object_storage) on the object-storage side."""
    if not dimension_tables_loaded(dim_conn, expected_orders_rows):
        return False
    return con.execute("SELECT count(*) FROM glob(getvariable('lineitem_probe_glob'))").fetchone()[0] > 0


def azure_blob_exists(container, account_name, account_key):
    from azure.storage.blob import BlobServiceClient

    conn_str = (
        f"DefaultEndpointsProtocol=https;AccountName={account_name};"
        f"AccountKey={account_key};EndpointSuffix=core.windows.net"
    )
    try:
        client = BlobServiceClient.from_connection_string(conn_str)
        return client.get_blob_client(container, "lineitem.parquet").exists()
    except Exception as e:  # noqa: BLE001 -- any failure here just means "not confirmed loaded yet"
        log(f"Azure blob existence check failed ({e}) -- treating as not loaded")
        return False


def configure_duckdb_object_storage(con, provider, bucket, endpoint, region, access_key, secret_key, path_style):
    con.execute("INSTALL httpfs; LOAD httpfs;")
    if provider == "s3":
        url_style = "path" if str(path_style).lower() in ("1", "true", "yes") else "vhost"
        if access_key:
            cred_clause = f"KEY_ID '{access_key}', SECRET '{secret_key}',"
        else:
            # No literal key pair configured -- real AWS IAM-role/instance-profile/env-credential
            # resolution via DuckDB's own credential_chain provider, instead of failing on an
            # empty KEY_ID (the recommended path for real AWS deployments; see .env.aws.example).
            cred_clause = "PROVIDER credential_chain,"
        secret_sql = f"""
            CREATE OR REPLACE SECRET tpch_s3 (
                TYPE s3,
                {cred_clause}
                REGION '{region}',
                URL_STYLE '{url_style}'
                {f", ENDPOINT '{endpoint.replace('http://', '').replace('https://', '')}'" if endpoint else ""}
                {", USE_SSL false" if endpoint and endpoint.startswith("http://") else ""}
            )
        """
        con.execute(secret_sql)
        con.execute(f"SET VARIABLE lineitem_probe_glob = 's3://{bucket}/lineitem.parquet'")
        return f"s3://{bucket}/lineitem.parquet"
    raise ValueError(f"unsupported provider for the DuckDB-direct upload path: {provider}")


def upload_lineitem_azure(con, bucket_container, account_name, account_key, sf):
    # Azure Blob has no DuckDB-native write-direct path configured here (kept simple: generate to
    # a local temp Parquet file, then upload via the real azure-storage-blob SDK) -- a real,
    # disclosed asymmetry with the S3-compatible path above, not an oversight.
    from azure.storage.blob import BlobServiceClient

    tmp_path = "/tmp/lineitem.parquet"
    log(f"generating LINEITEM (scale factor {sf}) to a local temp file for Azure upload...")
    con.execute(f"COPY lineitem TO '{tmp_path}' (FORMAT PARQUET)")
    conn_str = (
        f"DefaultEndpointsProtocol=https;AccountName={account_name};"
        f"AccountKey={account_key};EndpointSuffix=core.windows.net"
    )
    client = BlobServiceClient.from_connection_string(conn_str)
    container_client = client.get_container_client(bucket_container)
    try:
        container_client.create_container()
    except Exception:  # noqa: BLE001 -- already exists is the common, harmless case
        pass
    with open(tmp_path, "rb") as f:
        container_client.upload_blob(name="lineitem.parquet", data=f, overwrite=True)
    log(f"uploaded lineitem.parquet to Azure container '{bucket_container}'")


def load_dimension_tables(con, dim_conn):
    with dim_conn.cursor() as cur:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS region (r_regionkey INTEGER PRIMARY KEY, r_name CHAR(25), r_comment VARCHAR(152));
            CREATE TABLE IF NOT EXISTS nation (n_nationkey INTEGER PRIMARY KEY, n_name CHAR(25), n_regionkey INTEGER REFERENCES region, n_comment VARCHAR(152));
            CREATE TABLE IF NOT EXISTS supplier (s_suppkey INTEGER PRIMARY KEY, s_name CHAR(25), s_address VARCHAR(40), s_nationkey INTEGER REFERENCES nation, s_phone CHAR(15), s_acctbal DECIMAL(15,2), s_comment VARCHAR(101));
            CREATE TABLE IF NOT EXISTS part (p_partkey INTEGER PRIMARY KEY, p_name VARCHAR(55), p_mfgr CHAR(25), p_brand CHAR(10), p_type VARCHAR(25), p_size INTEGER, p_container CHAR(10), p_retailprice DECIMAL(15,2), p_comment VARCHAR(23));
            CREATE TABLE IF NOT EXISTS partsupp (ps_partkey INTEGER REFERENCES part, ps_suppkey INTEGER REFERENCES supplier, ps_availqty INTEGER, ps_supplycost DECIMAL(15,2), ps_comment VARCHAR(199), PRIMARY KEY (ps_partkey, ps_suppkey));
            CREATE TABLE IF NOT EXISTS customer (c_custkey INTEGER PRIMARY KEY, c_name VARCHAR(25), c_address VARCHAR(40), c_nationkey INTEGER REFERENCES nation, c_phone CHAR(15), c_acctbal DECIMAL(15,2), c_mktsegment CHAR(10), c_comment VARCHAR(117));
            CREATE TABLE IF NOT EXISTS orders (o_orderkey BIGINT PRIMARY KEY, o_custkey INTEGER REFERENCES customer, o_orderstatus CHAR(1), o_totalprice DECIMAL(15,2), o_orderdate DATE, o_orderpriority CHAR(15), o_clerk CHAR(15), o_shippriority INTEGER, o_comment VARCHAR(79));
        """)
        dim_conn.commit()
    for table in DIMENSION_TABLES:
        log(f"loading dimension table '{table}' into Postgres...")
        buf = io.StringIO()
        con.execute(f"COPY {table} TO '/tmp/{table}.csv' (FORMAT CSV, HEADER false)")
        with dim_conn.cursor() as cur, open(f"/tmp/{table}.csv") as f:
            cur.execute(f"TRUNCATE {table} CASCADE")
            cur.copy_expert(f"COPY {table} FROM STDIN WITH (FORMAT csv)", f)
        dim_conn.commit()


def main():
    sf = float(env("TPCH_SCALE_FACTOR", "1"))
    force = str(env("TPCH_FORCE_RELOAD", "false")).lower() in ("1", "true", "yes")

    dim_jdbc = env("TPCH_DIM_JDBC_URL", required=True)  # jdbc:postgresql://host:port/db?params
    dim_user = env("TPCH_DIM_USER", required=True)
    dim_password = env("TPCH_DIM_PASSWORD", required=True)
    dim_dsn = jdbc_to_psycopg2_dsn(dim_jdbc, dim_user, dim_password)

    provider = env("TPCH_LINEITEM_PROVIDER", "s3")
    bucket = env("TPCH_LINEITEM_BUCKET", required=True)

    con = duckdb.connect()
    con.execute("INSTALL tpch; LOAD tpch;")

    expected_orders_rows = int(1_500_000 * sf)

    dim_conn = wait_for_postgres(dim_dsn)

    if provider == "s3":
        lineitem_uri = configure_duckdb_object_storage(
            con, "s3", bucket,
            env("TPCH_LINEITEM_ENDPOINT", ""),
            env("TPCH_LINEITEM_REGION", "us-east-1"),
            env("TPCH_LINEITEM_ACCESS_KEY_ID", ""),
            env("TPCH_LINEITEM_SECRET_ACCESS_KEY", ""),
            env("TPCH_LINEITEM_PATH_STYLE", "true"),
        )
        if not force and already_loaded(con, dim_conn, expected_orders_rows):
            log("TPC-H data already present at the configured targets -- skipping generation (set "
                "TPCH_FORCE_RELOAD=true to reload anyway).")
            return
    elif provider == "azureblob":
        azure_account = env("TPCH_LINEITEM_AZURE_ACCOUNT_NAME", required=True)
        azure_key = env("TPCH_LINEITEM_AZURE_ACCOUNT_KEY", required=True)
        if not force and azure_blob_exists(bucket, azure_account, azure_key) \
                and dimension_tables_loaded(dim_conn, expected_orders_rows):
            log("TPC-H data already present at the configured targets -- skipping generation (set "
                "TPCH_FORCE_RELOAD=true to reload anyway).")
            return
    else:
        log(f"unknown TPCH_LINEITEM_PROVIDER '{provider}' -- expected 's3' or 'azureblob'")
        sys.exit(1)

    log(f"generating TPC-H scale factor {sf} (~{sf:.1f} GB) via DuckDB's real tpch extension...")
    start = time.time()
    con.execute(f"CALL dbgen(sf={sf})")
    log(f"generation finished in {time.time() - start:.0f}s")

    if provider == "s3":
        log(f"writing lineitem to {lineitem_uri} ...")
        con.execute(f"COPY lineitem TO '{lineitem_uri}' (FORMAT PARQUET)")
    elif provider == "azureblob":
        upload_lineitem_azure(
            con, bucket,
            env("TPCH_LINEITEM_AZURE_ACCOUNT_NAME", required=True),
            env("TPCH_LINEITEM_AZURE_ACCOUNT_KEY", required=True),
            sf,
        )
    else:
        log(f"unknown TPCH_LINEITEM_PROVIDER '{provider}' -- expected 's3' or 'azureblob'")
        sys.exit(1)

    load_dimension_tables(con, dim_conn)
    log("TPC-H dataset generation and load complete.")


def jdbc_to_psycopg2_dsn(jdbc_url, user, password):
    # Minimal, real parse of this project's own jdbc:postgresql://host:port/db?params shape --
    # not a general JDBC URL parser, scoped exactly to what TPCH_DIM_JDBC_URL is documented to carry.
    rest = jdbc_url.removeprefix("jdbc:postgresql://")
    hostport_db, _, query = rest.partition("?")
    hostport, _, db = hostport_db.partition("/")
    host, _, port = hostport.partition(":")
    dsn = f"host={host} port={port or 5432} dbname={db.split('?')[0]} user={user} password={password}"
    for param in query.split("&"):
        if param.startswith("currentSchema="):
            dsn += f" options=-c search_path={param.split('=', 1)[1]}"
    return dsn


def wait_for_postgres(dsn, attempts=30, delay_seconds=2):
    last_error = None
    for _ in range(attempts):
        try:
            return psycopg2.connect(dsn)
        except Exception as e:  # noqa: BLE001
            last_error = e
            time.sleep(delay_seconds)
    log(f"could not connect to the dimension-table database after {attempts} attempts: {last_error}")
    sys.exit(1)


if __name__ == "__main__":
    main()
