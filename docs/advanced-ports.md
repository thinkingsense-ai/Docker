# Advanced: ports

By default ThinkingSense serves everything on one port, `8080` — the admin console at `/admin`,
Ask at `/`. Most deployments never need anything beyond that. This page covers the two cases that
do.

## Putting Ask on its own separate port

Do this only if you want to expose Ask to the public internet while keeping the admin console
reachable only from inside your own network. Set `OMNIGATE_ASK_PORT` alongside the existing
`OMNIGATE_HTTP_PORT`:

```yaml
environment:
  OMNIGATE_HTTP_PORT: "8080"   # admin console + /api + /app only, once ASK_PORT is set
  OMNIGATE_ASK_PORT: "8081"    # Ask only
ports:
  - "8080:8080"
  - "8081:8081"
```

This is a hard split, not a mirror: once `OMNIGATE_ASK_PORT` is set, port `8080` stops serving
Ask's own routes (404s them) and port `8081` stops serving `/admin`/admin API routes (404s
those). Leave `OMNIGATE_ASK_PORT` unset (the default in this repo's `docker-compose.yml`) to keep
the single-port behavior.

## Every port this image can expose

| Port | Protocol | Purpose |
|---|---|---|
| `8080` | HTTP | Admin console (`/admin`) + Ask (`/`) + API — unless split, see above |
| `8081` | HTTP | Ask only, when `OMNIGATE_ASK_PORT` is set |
| `8443` | HTTPS | Same as `8080`, when TLS is configured (`OMNIGATE_TLS_*`) |
| `5433` | Postgres wire | Query any registered backend using a plain `psql`/Postgres client |
| `3306` | MySQL wire | Same, using a MySQL client |
| `1521` | Oracle wire | Same, using an Oracle client |
| `7070` | gRPC | Native driver, if you're using ThinkingSense's own driver instead of a wire-protocol client |
| `2484` | TCP | Oracle TLS variant, when TLS is configured |
