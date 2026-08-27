# Ansible and Server Convergence Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the repository and all six MTProto servers converge on a private Telemt API, one 2 GiB swap file, safe Telemt-created file modes, the new application checkout, and no obsolete deployment artifacts.

**Architecture:** Ansible remains the only steady-state deployment mechanism and processes one server at a time. The Telemt configuration migration edits only explicitly managed keys while preserving live users; destructive host cleanup occurs only after health checks and a recoverable backup.

**Tech Stack:** Ansible, systemd, Python/Jinja migration script, pytest, Docker Compose, Ubuntu swap tools.

**Spec:** `docs/superpowers/specs/2026-08-27-ansible-server-convergence-design.md`

## Global Constraints

- Work in the current checkout; creating a Git worktree is prohibited.
- Preserve `/opt/mtproto/telemt/telemt.toml`, all live Telemt users, and active Telemt state.
- Do not change the fixed `application` user or secret in this change.
- Keep `serial: 1` and `any_errors_fatal: true`.
- Do not deploy unpushed application content: the role clones `origin/main`.
- Stop the rollout immediately if any host fails verification.
- Enumerate every destructive cleanup target before deleting it.

---

### Task 1: Capture the Successful Private-API Canary

**Files:**
- Modify: `deploy/roles/mtproto_deploy/defaults/main.yml`
- Modify: `deploy/roles/mtproto_deploy/templates/configure-telemt.py.j2`
- Modify: `deploy/roles/mtproto_deploy/tasks/main.yml`
- Modify: `deploy/tests/test_deploy.py`

**Interfaces:**
- Consumes: `ansible_facts["default_ipv4"]["address"]`, Docker host gateway `172.17.0.1`.
- Produces: `telemt_api_listen: str` and `telemt_api_whitelist: list[str]`; an idempotent `[server.api]` migration.

- [x] **Step 1: Write and run the failing migration test**

Use a source configuration with `listen = "0.0.0.0:9091"` and
`whitelist = []`. Require this literal result:

```python
assert config["server"]["api"]["listen"] == "172.17.0.1:9091"
assert config["server"]["api"]["whitelist"] == [
    "172.16.0.0/12",
    "203.0.113.10/32",
]
```

Evidence already observed: the test failed because the migration preserved the
public listener.

- [x] **Step 2: Implement the minimal API migration**

Defaults:

```yaml
telemt_api_listen: 172.17.0.1:9091
telemt_api_whitelist:
  - 172.16.0.0/12
  - '{{ ansible_facts["default_ipv4"]["address"] }}/32'
```

The rendered script calls `configure_section()` for `server.api` with only
`listen` and `whitelist`. The direct Ansible probe uses
`http://{{ telemt_api_listen }}/v1/users/__ansible_connectivity_probe__`.

- [x] **Step 3: Verify the corrected canary on `vds6`**

Observed results:

```text
listener: 172.17.0.1:9091
host Telemt healthcheck: 0
container /v1/health: 200
FastAPI missing-user probe: 404
public /v1/health: no HTTP response
pre-existing users preserved: 289/289
```

- [ ] **Step 4: Review and commit the complete existing deployment migration**

Run:

```bash
uv run pytest deploy/tests -q
ANSIBLE_LOCAL_TEMP=/tmp/ansible-local-verify \
  ansible-playbook -i deploy/inventory.example.ini deploy/playbook.yml \
  --syntax-check
git diff --check
git diff --stat
git diff
```

Confirm the diff contains the already-reviewed Caddy removal, checkout split,
external TLS masking, private API migration, `vds6` inventory addition, and no
secret inventory data. Then commit the current migration files:

```bash
git add README.md deploy docs/ARCHITECTURE.md docs/DEPLOY.md \
  telemt/telemt.example.toml
git commit -m "refactor: converge telemt host deployment"
```

Do not push yet; Tasks 2–4 add follow-up commits before rollout.

### Task 2: Keep Telemt-Owned Files Private and Writable

**Files:**
- Modify: `deploy/roles/mtproto_deploy/templates/telemt.service.j2`
- Modify: `deploy/roles/mtproto_deploy/defaults/main.yml`
- Modify: `deploy/roles/mtproto_deploy/tasks/main.yml`
- Test: `deploy/tests/test_deploy.py`

**Interfaces:**
- Consumes: `telemt_config_dir` and the `telemt` service account.
- Produces: `telemt_beobachten_path: str`; systemd `UMask=0027`; conditional ownership repair for an existing snapshot.

- [ ] **Step 1: Write failing tests for the unit and existing snapshot task**

Extend the rendered-unit behavior test:

```python
assert "UMask=0027" in unit
```

Add a task-list test that runs `ansible-playbook --list-tasks` and requires
these task names:

```python
assert "Inspect Telemt beobachten snapshot" in result.stdout
assert "Repair Telemt beobachten snapshot ownership" in result.stdout
```

Run:

```bash
uv run pytest \
  deploy/tests/test_deploy.py::test_systemd_unit_grants_only_bind_service_capability \
  deploy/tests/test_deploy.py::test_deploy_playbook_contains_steady_state_services_without_legacy_tasks \
  -q
```

Expected: FAIL because the unit has no `UMask` and the tasks do not exist.

- [ ] **Step 2: Implement the minimal ownership and mode policy**

Add the default:

```yaml
telemt_beobachten_path: "{{ telemt_config_dir }}/beobachten.txt"
```

Add to the systemd `[Service]` section:

```ini
UMask=0027
```

Before the handler flush, add:

```yaml
- name: Inspect Telemt beobachten snapshot
  ansible.builtin.stat:
    path: "{{ telemt_beobachten_path }}"
  register: telemt_beobachten

- name: Repair Telemt beobachten snapshot ownership
  ansible.builtin.file:
    path: "{{ telemt_beobachten_path }}"
    state: file
    owner: telemt
    group: telemt
    mode: "0640"
  when: telemt_beobachten.stat.exists
```

- [ ] **Step 3: Run focused and full tests**

Run:

```bash
uv run pytest deploy/tests -q
ANSIBLE_LOCAL_TEMP=/tmp/ansible-local-verify \
  ansible-playbook -i deploy/inventory.example.ini deploy/playbook.yml \
  --syntax-check
git diff --check
```

Expected: all tests pass and syntax check exits `0`.

- [ ] **Step 4: Canary the mode policy on `vds6`**

Back up the current unit, deploy only `vds6`, and verify:

```bash
ansible -i deploy/inventory.ini vds6 -m ansible.builtin.copy \
  -a 'src=/etc/systemd/system/telemt.service dest=/var/backups/telemt.service.pre-umask-20260828 remote_src=true force=false owner=root group=root mode=0600'
ansible-playbook -i deploy/inventory.ini deploy/playbook.yml --limit vds6
ansible -i deploy/inventory.ini vds6 -m ansible.builtin.shell -a '
systemctl show telemt -p UMask --value
stat -c "%a %U:%G" /opt/mtproto/telemt/telemt.toml
/usr/local/bin/telemt healthcheck /opt/mtproto/telemt/telemt.toml --mode liveness
journalctl -u telemt --since "10 minutes ago" --no-pager | grep -c "Failed to flush beobachten snapshot" || true
'
```

Expected: `0027`, `640 telemt:telemt`, healthcheck exit `0`, and zero new
snapshot permission errors.

- [ ] **Step 5: Commit**

```bash
git add deploy/roles/mtproto_deploy/defaults/main.yml \
  deploy/roles/mtproto_deploy/tasks/main.yml \
  deploy/roles/mtproto_deploy/templates/telemt.service.j2 \
  deploy/tests/test_deploy.py
git commit -m "fix: preserve private telemt file modes"
```

### Task 3: Converge Swap Safely

**Files:**
- Create: `deploy/roles/mtproto_deploy/tasks/configure_swap.yml`
- Modify: `deploy/roles/mtproto_deploy/tasks/main.yml`
- Modify: `deploy/roles/mtproto_deploy/defaults/main.yml`
- Test: `deploy/tests/test_deploy.py`

**Interfaces:**
- Consumes: `mtproto_swap_size_mb: int`.
- Produces: `mtproto_swap_path: str`, `mtproto_temporary_swap_path: str`; one active 2048 MiB `/swapfile` and one canonical fstab line.

- [ ] **Step 1: Write a failing task-list contract test**

Require the rendered playbook task list to contain:

```python
for task_name in (
    "Read canonical swap size",
    "Check disk space for swap replacement",
    "Activate temporary replacement swap",
    "Replace incorrectly sized canonical swap",
    "Remove legacy extra swap",
    "Persist canonical swap in fstab",
):
    assert task_name in result.stdout
```

Also assert the role defaults render these literal paths:

```python
assert mtproto_swap_path == "/swapfile"
assert mtproto_temporary_swap_path == "/swapfile.ansible-replacement"
```

Run the focused test and expect failure because the task file and defaults do
not exist.

- [ ] **Step 2: Extract existing swap tasks into `configure_swap.yml`**

Replace the inline swap block in `tasks/main.yml` with:

```yaml
- name: Configure canonical swap
  ansible.builtin.import_tasks: configure_swap.yml
```

Add defaults:

```yaml
mtproto_swap_path: /swapfile
mtproto_temporary_swap_path: /swapfile.ansible-replacement
mtproto_legacy_swap_paths:
  - /2G_swapfile
```

- [ ] **Step 3: Implement size discovery and disk-space validation**

Start `configure_swap.yml` with the complete discovery and validation block:

```yaml
- name: Set canonical swap target size
  ansible.builtin.set_fact:
    mtproto_swap_target_bytes: "{{ mtproto_swap_size_mb | int * 1024 * 1024 }}"

- name: Inspect canonical swap file
  ansible.builtin.stat:
    path: "{{ mtproto_swap_path }}"
  register: mtproto_swapfile

- name: Read canonical swap size
  ansible.builtin.command:
    argv: [stat, -c, "%s", "{{ mtproto_swap_path }}"]
  register: mtproto_swap_size
  changed_when: false
  when: mtproto_swapfile.stat.exists

- name: Record whether canonical swap needs replacement
  ansible.builtin.set_fact:
    mtproto_swap_needs_replacement: >-
      {{ mtproto_swapfile.stat.exists and
         mtproto_swap_size.stdout | int != mtproto_swap_target_bytes | int }}

- name: Check disk space for swap replacement
  ansible.builtin.command: df --output=avail -B1 /
  register: mtproto_swap_disk_space
  changed_when: false
  when: mtproto_swap_needs_replacement

- name: Require disk space for swap replacement
  ansible.builtin.assert:
    that:
      - mtproto_swap_disk_space.stdout_lines[-1] | int >=
        (mtproto_swap_target_bytes | int * 2)
    fail_msg: >-
      Replacing {{ mtproto_swap_path }} requires at least
      {{ mtproto_swap_target_bytes | int * 2 }} free bytes on /.
  when: mtproto_swap_needs_replacement
```

The conservative two-file requirement prevents a partial replacement caused
by disk exhaustion.

- [ ] **Step 4: Implement the recoverable replacement sequence**

Append the following tasks. This also resumes safely if an earlier run left the
temporary swap active:

```yaml
- name: Read active swap devices before replacement
  ansible.builtin.command: swapon --show=NAME --noheadings
  register: mtproto_active_swaps_before
  changed_when: false

- name: Disable stale temporary replacement swap
  ansible.builtin.command:
    argv: [swapoff, "{{ mtproto_temporary_swap_path }}"]
  when:
    - mtproto_swap_needs_replacement
    - mtproto_temporary_swap_path in
      (mtproto_active_swaps_before.stdout_lines | map('trim') | list)

- name: Remove stale temporary replacement swap
  ansible.builtin.file:
    path: "{{ mtproto_temporary_swap_path }}"
    state: absent
  when: mtproto_swap_needs_replacement

- name: Allocate temporary replacement swap
  ansible.builtin.command:
    argv: [fallocate, -l, "{{ mtproto_swap_size_mb }}M", "{{ mtproto_temporary_swap_path }}"]
  when: mtproto_swap_needs_replacement

- name: Protect temporary replacement swap
  ansible.builtin.file:
    path: "{{ mtproto_temporary_swap_path }}"
    owner: root
    group: root
    mode: "0600"
  when: mtproto_swap_needs_replacement

- name: Format temporary replacement swap
  ansible.builtin.command:
    argv: [mkswap, "{{ mtproto_temporary_swap_path }}"]
  when: mtproto_swap_needs_replacement

- name: Activate temporary replacement swap
  ansible.builtin.command:
    argv: [swapon, "{{ mtproto_temporary_swap_path }}"]
  when: mtproto_swap_needs_replacement

- name: Disable incorrectly sized canonical swap
  ansible.builtin.command:
    argv: [swapoff, "{{ mtproto_swap_path }}"]
  when:
    - mtproto_swap_needs_replacement
    - mtproto_swap_path in
      (mtproto_active_swaps_before.stdout_lines | map('trim') | list)

- name: Remove incorrectly sized canonical swap
  ansible.builtin.file:
    path: "{{ mtproto_swap_path }}"
    state: absent
  when: mtproto_swap_needs_replacement

- name: Replace incorrectly sized canonical swap
  ansible.builtin.command:
    argv: [fallocate, -l, "{{ mtproto_swap_size_mb }}M", "{{ mtproto_swap_path }}"]
  when: mtproto_swap_needs_replacement

- name: Create missing canonical swap
  ansible.builtin.command:
    argv: [fallocate, -l, "{{ mtproto_swap_size_mb }}M", "{{ mtproto_swap_path }}"]
  when: not mtproto_swapfile.stat.exists

- name: Protect canonical swap
  ansible.builtin.file:
    path: "{{ mtproto_swap_path }}"
    owner: root
    group: root
    mode: "0600"

- name: Format new canonical swap
  ansible.builtin.command:
    argv: [mkswap, "{{ mtproto_swap_path }}"]
  when: mtproto_swap_needs_replacement or not mtproto_swapfile.stat.exists

- name: Read active swap devices before canonical activation
  ansible.builtin.command: swapon --show=NAME --noheadings
  register: mtproto_active_swaps_for_activation
  changed_when: false

- name: Activate canonical swap
  ansible.builtin.command:
    argv: [swapon, "{{ mtproto_swap_path }}"]
  when: >-
    mtproto_swap_path not in
    (mtproto_active_swaps_for_activation.stdout_lines | map('trim') | list)

- name: Disable temporary replacement swap
  ansible.builtin.command:
    argv: [swapoff, "{{ mtproto_temporary_swap_path }}"]
  when: mtproto_swap_needs_replacement

- name: Remove temporary replacement swap
  ansible.builtin.file:
    path: "{{ mtproto_temporary_swap_path }}"
    state: absent
  when: mtproto_swap_needs_replacement
```

A failure before canonical activation leaves temporary swap active. A failure
after canonical activation cannot remove the canonical file because all
following tasks touch only the temporary or known legacy paths.

- [ ] **Step 5: Remove legacy swap and normalize fstab**

Append the concrete legacy cleanup and persistence tasks:

```yaml
- name: Read active swap devices before legacy cleanup
  ansible.builtin.command: swapon --show=NAME --noheadings
  register: mtproto_active_swaps_for_cleanup
  changed_when: false

- name: Disable legacy extra swap
  ansible.builtin.command:
    argv: [swapoff, "{{ item }}"]
  loop: "{{ mtproto_legacy_swap_paths }}"
  when: >-
    item in
    (mtproto_active_swaps_for_cleanup.stdout_lines | map('trim') | list)

- name: Remove legacy extra swap
  ansible.builtin.file:
    path: "{{ item }}"
    state: absent
  loop: "{{ mtproto_legacy_swap_paths }}"

- name: Remove managed swap lines from fstab
  ansible.builtin.replace:
    path: /etc/fstab
    regexp: '^(?!#)(?:/swapfile|/2G_swapfile)\s+.*\n?'
    replace: ""

- name: Persist canonical swap in fstab
  ansible.builtin.lineinfile:
    path: /etc/fstab
    line: /swapfile none swap sw 0 0
    state: present
```

- [ ] **Step 6: Run focused and full verification**

Run:

```bash
uv run pytest deploy/tests -q
ANSIBLE_LOCAL_TEMP=/tmp/ansible-local-verify \
  ansible-playbook -i deploy/inventory.example.ini deploy/playbook.yml \
  --syntax-check
git diff --check
```

Expected: all tests pass.

- [ ] **Step 7: Check real disk capacity before any swap deployment**

Run read-only collection:

```bash
ansible -i deploy/inventory.ini mtproto_servers -m ansible.builtin.shell -a '
df --output=avail -B1 / | tail -1
swapon --show=NAME,SIZE --noheadings
'
```

Require at least 4294967296 available bytes on every server that needs
replacement. Stop and revise the approach for any host below the threshold.

- [ ] **Step 8: Canary swap convergence on `vds6`**

Deploy `vds6`, then verify:

```bash
ansible-playbook -i deploy/inventory.ini deploy/playbook.yml --limit vds6
ansible -i deploy/inventory.ini vds6 -m ansible.builtin.shell -a '
swapon --show=NAME,SIZE --bytes --noheadings
awk "!/^#/ && /swap/" /etc/fstab
stat -c "%s %a" /swapfile
'
```

Expected: only `/swapfile`, size `2147483648`, mode `600`, and one canonical
fstab line.

- [ ] **Step 9: Commit**

```bash
git add deploy/roles/mtproto_deploy/defaults/main.yml \
  deploy/roles/mtproto_deploy/tasks/main.yml \
  deploy/roles/mtproto_deploy/tasks/configure_swap.yml \
  deploy/tests/test_deploy.py
git commit -m "fix: converge canonical swap state"
```

### Task 4: Remove Legacy Test Noise and Finish Documentation

**Files:**
- Modify: `deploy/tests/test_deploy.py`
- Modify: `docs/DEPLOY.md`
- Modify: `docs/ARCHITECTURE.md`
- Modify: `README.md`

**Interfaces:**
- Consumes: the final task names, paths, and API settings from Tasks 1–3.
- Produces: a focused regression suite and operator instructions matching the role.

- [ ] **Step 1: Remove negative legacy-only tests**

Delete:

- `test_repository_has_no_one_shot_cleanup_playbook_or_role`;
- the obsolete host-variable key absence loop;
- the negative `legacy_task_name` loop inside the task-list test.

These tests only fail when historical names reappear and do not exercise
runtime behavior.

- [ ] **Step 2: Consolidate migration tests**

Keep `test_steady_state_migration_enforces_external_beatvault_profile` as the
single comprehensive migration test. Ensure its input includes all removed
keys:

```toml
client_mss = "tspu"
client_mss_bulk = "1400"
tls_domains = ["old.example"]
mask_host = "127.0.0.1"
```

It must assert private API settings, external TLS settings, unrelated field
preservation, user preservation, and second-run idempotence. Delete later tests
that repeat only subsets of this contract.

- [ ] **Step 3: Update operational documentation**

Document these exact states:

```text
Telemt API bind: 172.17.0.1:9091
Docker whitelist: 172.16.0.0/12
Host healthcheck whitelist: host default IPv4 /32
Canonical swap: /swapfile, 2048 MiB
Telemt-created file umask: 0027
Application checkout: /opt/mtproto-app
Mutable config: /opt/mtproto/telemt/telemt.toml
```

State that public port 9091 must produce no HTTP response.

- [ ] **Step 4: Run complete local verification**

Run:

```bash
uv run pytest -q
ANSIBLE_LOCAL_TEMP=/tmp/ansible-local-verify \
  ansible-playbook -i deploy/inventory.example.ini deploy/playbook.yml \
  --syntax-check
git diff --check
```

Expected: all tests pass, syntax check exits `0`, no whitespace errors.

- [ ] **Step 5: Commit**

```bash
git add deploy/tests/test_deploy.py README.md docs/ARCHITECTURE.md docs/DEPLOY.md
git commit -m "test: remove legacy deployment assertions"
```

### Task 5: Push the Reproducible Source of Truth

**Files:**
- Verify only: entire repository.

**Interfaces:**
- Consumes: commits from Tasks 1–4.
- Produces: `origin/main` containing every file the server-side checkout needs.

- [ ] **Step 1: Verify the exact commit range and clean tracked state**

Run:

```bash
git status --short --branch
git log --oneline --decorate -8
git diff origin/main...HEAD --stat
git diff origin/main...HEAD
uv run pytest -q
ANSIBLE_LOCAL_TEMP=/tmp/ansible-local-verify \
  ansible-playbook -i deploy/inventory.example.ini deploy/playbook.yml \
  --syntax-check
git diff --check
```

Confirm no inventory, secret, `.env`, cache, or unrelated file is staged or
committed.

- [ ] **Step 2: Push `main`**

Run:

```bash
git push origin main
git rev-parse HEAD
git ls-remote origin refs/heads/main
```

Expected: the local and remote commit hashes are identical.

### Task 6: Roll Out and Clean `vds1` Through `vds5`

**Files:**
- No repository changes expected.
- Remote backups: `/var/backups/telemt.toml.pre-convergence-20260828` and `/var/backups/telemt.service.pre-convergence-20260828`.

**Interfaces:**
- Consumes: pushed `origin/main` and verified canary state.
- Produces: five converged hosts plus the existing `vds6` canary.

- [ ] **Step 1: Record and validate cleanup targets without deleting**

For `vds1` through `vds5`, list:

```bash
ansible -i deploy/inventory.ini 'vds1:vds2:vds3:vds4:vds5' \
  -m ansible.builtin.shell -a '
find /opt/mtproto -maxdepth 3 -mindepth 1 -printf "%y %p\n" | sort
'
```

For each host, copy only paths matching the approved classes into a separate
controller-side file `/tmp/HOST-cleanup-paths`. The file must contain explicit
absolute paths, one per line; never put a directory containing the live config
in it. Review it with:

```bash
sed -n '1,200p' /tmp/HOST-cleanup-paths
rg -n '(^|/)telemt\.toml$|beobachten\.txt$' /tmp/HOST-cleanup-paths
```

The second command must find nothing. Preserve `beobachten.txt`: after the
ownership repair it is treated as active Telemt state unless a separate audit
proves that Telemt no longer creates or updates it.

- [ ] **Step 2: Create per-host recovery backups**

Use `ansible.builtin.copy` with `remote_src=true`, `force=false`, owner/group
`root`, and mode `0600` to back up both the config and systemd unit. Verify each
backup with `stat` before deployment.

- [ ] **Step 3: Deploy one host at a time**

For each host in `vds1 vds2 vds3 vds4 vds5`, run:

```bash
ansible-playbook -i deploy/inventory.ini deploy/playbook.yml --limit HOST
```

Do not start the next host until Step 4 succeeds for the current host.

- [ ] **Step 4: Verify the current host**

Check:

```text
telemt.service active and enabled
docker.service active and enabled
Telemt version 3.4.25
Telemt CLI liveness exit 0
TLS mask succeeds
172.17.0.1:9091 returns API responses from host and container
public HOST:9091 returns no HTTP response
FastAPI missing-user probe returns 404
/swapfile is the only active swap and is 2147483648 bytes
one canonical fstab swap line
telemt.toml is telemt:telemt 0640
no new beobachten permission errors
/opt/mtproto-app is at the pushed commit
```

On any failure, restore config and unit backups, restart Telemt, verify health,
and stop the rollout.

- [ ] **Step 5: Delete only the reviewed paths on the healthy host**

Read `/tmp/HOST-cleanup-paths` and invoke `ansible.builtin.file` with
`state=absent` once per explicit path. Do not use a shell glob, recursive `rm`,
or `/opt/mtproto` itself as a deletion target. The reviewed list may contain
only old checkout metadata/application paths, `telemt.toml.pre-*`,
`telemt.toml.post-*`, `docker-compose.yaml.before-*`, and `telemt/tlsfront`.
Preserve the live config, `beobachten.txt`, all current Telemt state, and the
root-only recovery backups. Save the successful Ansible result beside the
candidate list and report every deleted path with its recovery source (Git or
the root-only backup).

- [ ] **Step 6: Re-run host verification after cleanup**

Repeat Step 4. Continue only when all checks still pass.

### Task 7: Final Six-Host Audit

**Files:**
- No repository changes expected.

**Interfaces:**
- Consumes: all six deployed hosts.
- Produces: evidence that repository and runtime state agree.

- [ ] **Step 1: Run local verification from the pushed commit**

```bash
uv run pytest -q
ANSIBLE_LOCAL_TEMP=/tmp/ansible-local-final \
  ansible-playbook -i deploy/inventory.example.ini deploy/playbook.yml \
  --syntax-check
git diff --check
git status --short --branch
```

- [ ] **Step 2: Collect the final host matrix**

Collect for all hosts: checkout commit/path, service state, Telemt version,
listeners, API/TLS/FastAPI probes, swap layout, fstab, file modes, snapshot
errors, and legacy paths. Do not print Telemt secrets or complete proxy links.

- [ ] **Step 3: Verify public API closure externally**

From the controller, request `http://HOST:9091/v1/health` for all six hosts with
a four-second connect timeout. Expected: no host returns an HTTP status.

- [ ] **Step 4: Report completion with rollback locations**

Report test counts, pushed commit hash, each host's verified state, deleted
legacy artifacts, retained backups, and any remaining non-blocking warnings.
