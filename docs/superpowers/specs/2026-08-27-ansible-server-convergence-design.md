# Ansible and Server Convergence Design

## Goal

Make the Ansible deployment the reproducible source of truth for all six
MTProto servers while preserving live Telemt users and limiting disruption to
one server at a time.

The fixed application user and secret in the example configuration are outside
this change by explicit decision.

## Private Telemt API

Production Telemt binds its API to `172.17.0.1:9091`, the `docker0` address on
all six servers. The whitelist contains:

- `172.16.0.0/12` for the Docker networks used by the FastAPI containers;
- the server's `ansible_facts["default_ipv4"]["address"]` as a `/32`, allowing
  the Telemt CLI healthcheck executed on the host.

The production migration script manages only `listen` and `whitelist` inside
`[server.api]`. It preserves `enabled`, `read_only`, authentication, runtime
settings, users, and unrelated configuration. The local Docker Compose example
keeps `0.0.0.0:9091` because its Telemt process runs inside a container rather
than on the host.

The deployment verifies four paths:

1. Telemt CLI liveness from the host;
2. direct API access through `172.17.0.1:9091`;
3. FastAPI access through `host.docker.internal`;
4. lack of an HTTP response through the server's public address on port 9091.

The corrected configuration has already passed these checks as a canary on
`vds6`.

## Swap Convergence

The desired state is one active `/swapfile` of exactly 2048 MiB and one
canonical `/etc/fstab` entry:

```text
/swapfile none swap sw 0 0
```

When `/swapfile` has the wrong size, Ansible first creates and activates a
temporary 2048 MiB swap file. It then disables and replaces `/swapfile`,
activates the replacement, and removes the temporary file. This avoids
draining the old swap without replacement capacity.

After the canonical swap is active, Ansible disables and removes the known
legacy `/2G_swapfile` when present. It removes duplicate legacy swap entries
from `/etc/fstab` before adding the canonical line. Before replacement, Ansible
asserts that enough disk space is available for the temporary file.

## Telemt File Ownership and Modes

The systemd unit sets `UMask=0027`. Files created by Telemt through atomic
replacement therefore remain unreadable to other users. Ansible continues to
enforce `telemt:telemt` ownership and mode `0640` on `telemt.toml`.

If `beobachten.txt` exists, Ansible changes it to `telemt:telemt` mode `0640`.
It does not create the file on servers where Telemt has not created it. This
stops the current permission errors without inventing state Telemt may not
need.

## Repository Cleanup

Tests retain behavior that protects live configuration and deployment
connectivity. Tests that only assert the absence of historical files, variables,
or task names are removed. Repeated Telemt migration cases are consolidated
where they exercise the same behavior.

The complete local migration is reviewed, tested, committed, and pushed to
`origin/main` before deployment because the role clones that branch on each
server.

## Server Migration and Cleanup

Deployment remains `serial: 1` with `any_errors_fatal: true`. The rollout order
is `vds1` through `vds5`; `vds6` is already the canary. Each server must pass
Telemt liveness, TLS masking, direct API, FastAPI, swap, ownership, and public
port checks before the next server starts.

The new application checkout is `/opt/mtproto-app`. The live configuration
remains `/opt/mtproto/telemt/telemt.toml`.

After a server passes deployment checks, cleanup removes:

- the old `/opt/mtproto/.git` checkout metadata and old application files;
- known experimental `telemt.toml.pre-*` and `telemt.toml.post-*` files;
- `docker-compose.yaml.before-*` files;
- the legacy `telemt/tlsfront` directory;
- obsolete root-owned `beobachten.txt` only if Telemt no longer uses or updates
  it after the ownership fix.

Cleanup must explicitly preserve:

- `/opt/mtproto/telemt/telemt.toml`;
- any active Telemt state files;
- the root-only pre-rollout backup created for recovery.

Targets are enumerated and checked before deletion. Cleanup occurs only after
the replacement checkout and services are healthy.

## Rollback

Before changing each host, save `telemt.toml` as a root-owned mode `0600`
backup outside the application checkout. On any deployment or verification
failure:

1. restore that host's configuration;
2. restore the prior systemd unit when it changed;
3. restart Telemt;
4. verify Telemt liveness and FastAPI connectivity;
5. stop the serial rollout.

Swap replacement does not remove the old or temporary swap until the new file
is active. Legacy checkout cleanup runs only after rollback-sensitive service
changes have passed.

## Verification

Local verification consists of the complete pytest suite, Ansible syntax
check, and `git diff --check`. Server verification records service state,
listeners, Telemt version and health, FastAPI connectivity, swap layout,
configuration modes, legacy artifacts, and external port 9091 behavior for all
six hosts.
