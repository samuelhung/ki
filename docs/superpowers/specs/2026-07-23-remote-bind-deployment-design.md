# Remote Bind Deployment Design

## Goal

Deploy the backend and bundled Web UI atomically to the production Mac while preserving direct access at `http://10.8.0.105:9120`. Keep loopback binding as the default and require token-based access whenever deployment explicitly selects a non-loopback bind address.

## Deployment Contract

- Add `bind_host` to `BackendDeployConfig` and `--bind-host` to the deployment CLI.
- Keep the default bind host at `127.0.0.1`.
- Accept only IP literals or `localhost`; production uses `0.0.0.0`.
- Keep health checks on the independent loopback `health_origin`. A public bind address must never make deployment health checks depend on the network.
- Generate launchd arguments with the configured `--host` and the port derived from `health_origin`.

## Security Boundary

- Before any service stop, a non-loopback deployment must verify that `${ZHIJI_HOME}/.env` is a regular, non-symlink file with mode `0600` and a non-empty `KI_API_TOKEN` entry.
- The deployment tool validates presence only. It never prints, copies, accepts on the command line, or persists the token.
- Production configuration also sets `KI_ALLOWED_HOSTS` for `10.8.0.105`, loopback names, and the production host header.
- The local Vite proxy receives the matching token through ignored `app/frontend/.env.local`, also mode `0600`; browser bundles and logs never receive the token.
- Existing CLI and middleware enforcement remain authoritative at runtime.

## Migration Flow

1. Merge the deployment-contract change through CI.
2. Generate a random API token and atomically update the remote `${ZHIJI_HOME}/.env` without exposing the value in command output.
3. Write the same token to the ignored local Vite environment file with mode `0600`.
4. Rebuild and verify the backend wheel and `SHA256SUMS` from merged `main`.
5. Before the first atomic deployment only, copy the legacy `runtime/venv` into a versioned rollback snapshot and point `runtime/current` at that snapshot without moving or modifying the live legacy venv.
6. Upload the wheel, checksum file, and matching deployment script.
7. Run the atomic deployer with `--bind-host 0.0.0.0` and loopback health checks.
8. Verify loopback health, authenticated remote health, database integrity, current symlink, version, and the primary Web routes.

## Failure And Rollback

- Invalid bind hosts, missing or insecure `.env`, missing token, bad wheel, bad checksum, or an occupied target version fail before stopping the service.
- Startup or smoke-test failures restore the database backup, previous `current` target, and previous launchd configuration through the existing rollback path.
- The previous legacy `runtime/venv` installation remains intact during the first atomic migration. A copied versioned snapshot is the deployer's rollback target; the original path remains available until post-deployment verification is complete.
- No Sparkle, DMG, GitHub Release, tag, or Appcast operation is part of this deployment.

## Tests

- Default launchd output remains loopback-only.
- An explicit `0.0.0.0` bind is written to launchd only when a secure `.env` contains `KI_API_TOKEN`.
- Missing token, symlinked `.env`, insecure permissions, hostnames, malformed addresses, and command-line secret exposure are rejected before service stop.
- Health origin remains loopback-only and supplies the launchd port.
- Existing artifact, backup, rollback, retention, and smoke tests remain green.
- A production-like isolated deployment test verifies the versioned `current` switch without touching the real service or database.

## Out Of Scope

- TLS termination or a new reverse proxy.
- Sparkle desktop packaging and publication.
- Changing API response formats, SQLite schema, page behavior, or visual presentation.
