# Using this fixture with the Docker image (this repo)

The per-tier READMEs in this directory (and its `single-postgres/`/`csv-object-storage/`
subdirectories) show `java -jar ../../target/omnigate.jar` — that's the instruction for running
against a local build in the `Server` source repo. **In this Docker repo, run it via the image
instead**:

```bash
# Tier A (4 real database engines) -- bring up the fixture's own containers, then point the
# image's OMNIGATE_BACKENDS/OMNIGATE_ROUTER_SCHEMA_RULES at them (see fixtures/supply-chain/
# omnigate.env.example) instead of this repo's own docker-compose.yml Postgres service:
cd fixtures/supply-chain
docker compose up -d
./seed.sh
source omnigate.env.example
cd ../..
docker compose run --rm -e OMNIGATE_BACKENDS -e OMNIGATE_ROUTER_SCHEMA_RULES omnigate

# Tier B (single Postgres) -- reuse THIS repo's own seeded Postgres service instead of a separate
# one: seed fixtures/supply-chain/single-postgres/seed.sql into it, then set
# OMNIGATE_BACKENDS/OMNIGATE_ROUTER_SCHEMA_RULES from that tier's own omnigate.env.example
# (pointing HOST at "postgres", the service name in this repo's own docker-compose.yml).

# Tier C (CSV + Postgres) -- same idea: seed csv-object-storage/seed-postgres.sql into this
# repo's own Postgres service, mount csv-object-storage/ into the omnigate container (add a
# volume in docker-compose.yml), and set OMNIGATE_BACKENDS from that tier's own
# omnigate.env.example with CSV_DIR pointing at the mounted path inside the container.
```

See `../../README.md` (this repo's own top-level README) for the base `docker compose up --build`
quick start this fixture builds on top of.
