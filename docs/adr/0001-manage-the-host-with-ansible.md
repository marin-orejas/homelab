# 0001: Manage the host with Ansible and RHEL System Roles

Status: accepted

This record covers how the NUC's operating system is configured and how Ansible gets root. It is added with the Ansible layout in #17.

## Context

- The NUC runs RHEL 10.3. After the install, every setting was made by hand and is not recorded anywhere.
- A rebuild must give the same host, and every change must be reviewed in a PR and tested on a staging VM first.
- The control node is the Fedora desktop. The `lint` check runs on GitHub-hosted runners, which have no Red Hat login.
- Red Hat ships RHEL System Roles for SSH, firewalld, SELinux, crypto policies, time sync and journald. Red Hat tests them on RHEL 10.
- Puppet and Salt need an agent or a server on the host. Shell scripts are hard to run twice without side effects.
- Almost every role needs root. I run Ansible by hand, and no CI job or timer runs it.

## Decision

Ansible runs from the desktop over SSH and uses the System Roles from `fedora.linux_system_roles` on Galaxy, with own roles only where none exists. It connects as my own user and gets root through `sudo`, with the password asked on each run.

## Consequences

- Ansible is the only tool that changes the host, and every change goes through a PR.
- No agent and no extra server. SSH and Python on the host are enough.
- The upstream project maintains the roles, so the repo needs little own code.
- CI installs the collections from Galaxy without a secret.
- `fedora.linux_system_roles` is the upstream of `redhat.rhel_system_roles` and has no Red Hat support.
- A change made by hand stays until the next playbook run. There is no agent that reverts it.
- `dnf-automatic` and k3s have no System Role, so they need own roles.
- A stolen SSH key alone does not give root, because `sudo` still asks for the password.
- Every run needs me at the keyboard. Unattended runs need a dedicated user with `NOPASSWD` sudo and a new ADR.
