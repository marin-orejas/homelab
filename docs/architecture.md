# Architecture

This page shows the parts of the lab and how they connect. It covers the host layer, which Ansible configures from the desktop.

```mermaid
flowchart LR
    desktop["Fedora desktop: Ansible"] -- SSH --> nuc["NUC: RHEL 10"]
```

## Host

| Part | Value |
|---|---|
| Machine | NUC |
| OS | RHEL 10 |
| Network | Wi-Fi, static address `192.168.1.10` |
| Inventory name | `nuc-rhel` in the `production` group |

## Control node

Ansible runs on the Fedora desktop from a Python venv with the versions in `requirements-dev.txt`. These are the same versions that the `lint` check uses.

The NUC has no Ansible installed. It needs only SSH and Python.

## How a run works

- Every command runs from `ansible/`, where Ansible reads `ansible.cfg` and picks the `production` inventory.
- Ansible connects over SSH with the alias `nuc-rhel`. User, address and key come from `~/.ssh/config` on the desktop, not from the repo.
- On the NUC, it runs its modules with `/usr/bin/python3`, set in `group_vars/all.yml`.
- Tasks that need root use `sudo`. Ansible asks for the password at the start of each run, see [ADR 0001](adr/0001-manage-the-host-with-ansible.md).

## Ansible layout

| Path | Content |
|---|---|
| `ansible/ansible.cfg` | Default inventory, roles path, sudo password prompt |
| `ansible/requirements.yml` | Collections, each pinned to an exact version |
| `ansible/site.yml` | Entry point that imports the playbooks |
| `ansible/playbooks/host.yml` | Host configuration |
| `ansible/inventory/production/` | The NUC and its variables |

The System Roles come from `fedora.linux_system_roles`. Its dependencies `ansible.posix`, `community.general` and `containers.podman` are pinned too, so a clean install gets the same versions everywhere.
