# Homelab

![Status: in progress](https://img.shields.io/badge/status-in%20progress-bf8700?style=flat-square)

Single-node k3s lab on an Intel NUC, run with Ansible, Argo CD and pull requests to a protected main branch.
Version 2 is in progress, and version 1, a Docker Compose media server, is kept at the [v1.0.0 release](https://github.com/marin-orejas/homelab/releases/tag/v1.0.0).

## Highlights

- The host is a single Intel NUC on RHEL 10 with a static LAN address.
- Every change reaches `main` through a pull request and a squash merge.
- A required `lint` check runs yamllint and ansible-lint on each pull request.
- Version 1 ran 9 Docker containers and served 117 films and 10 series.

## Tech stack

| Layer | Tools |
|---|---|
| Host | RHEL 10, Ansible |
| Cluster | k3s |
| Delivery | Argo CD |
| CI | GitHub Actions, yamllint, ansible-lint |

## Project structure

| Folder | Contents |
|---|---|
| [`.github/`](.github/) | Lint workflow, issue and PR templates |
| [`docs/`](docs/) | [Workflow](docs/workflow.md): how a change reaches `main` |

## Roadmap

| Topic | Status |
|---|---|
| Foundation: repo reset, ruleset, issue template, CI lint | in progress |
| Host: Ansible hardening of the NUC | planned |

## License

No license yet, so all rights are reserved.
