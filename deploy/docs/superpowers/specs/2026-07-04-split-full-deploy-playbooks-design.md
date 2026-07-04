# Separate Full Deploy Playbooks Design

## Goal

Replace the shared `deploy/playbook.yml` entrypoint with explicit full deployment
playbooks for development and production. Every full deployment must install both
the MTProto application and the Docker-aware Telemt SYN limiter.

## Architecture

Move the tasks currently defined in `deploy/playbook.yml` into a reusable
`mtproto_deploy` Ansible role. Two thin playbooks will select the target inventory
group and compose roles in this order:

1. `mtproto_deploy`, which prepares the host, starts Docker, checks out the
   repository, and starts the Compose application.
2. `telemt_syn_limit`, which requires Docker's `DOCKER-USER` chain and installs
   and enables `telemt-syn-limit.service`.

The development entrypoint will be `deploy/playbook-dev.yml` and target only
`mtproto_dev`. The production entrypoint will be `deploy/playbook-prod.yml`,
target only `mtproto_prod`, and retain safe rolling behavior through `serial: 1`
and `any_errors_fatal: true`.

## Compatibility and Scope

Delete `deploy/playbook.yml`; no generic all-host compatibility entrypoint will
remain. Keep the existing limiter-only development, production, and rollback
playbooks so operators can manage the firewall mechanism independently of a full
application deployment.

The deployment task behavior and existing limiter defaults remain unchanged.
This change does not alter Telemt configuration, Docker Compose configuration,
or the limiter's rate, burst, port, or packet handling.

## Failure Behavior

Role order guarantees Docker is running before the limiter checks for the
`DOCKER-USER` chain. A missing chain remains a hard limiter installation failure.
Production hosts deploy one at a time, and any host failure stops the production
play.

## Testing and Documentation

Tests will assert that:

- the obsolete shared playbook is absent;
- dev and prod full playbooks target exactly their intended inventory groups;
- both full playbooks compose `mtproto_deploy` before `telemt_syn_limit`;
- production retains serial, fail-fast deployment;
- the reusable deployment role contains the application deployment behavior.

Update `docs/DEPLOY.md` to document the two full deployment commands and remove
instructions based on `deploy/playbook.yml`. Existing limiter-only and rollback
instructions remain available.
