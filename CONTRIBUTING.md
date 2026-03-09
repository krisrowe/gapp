# Contributing to gapp

This document covers the design, architecture, and principles behind gapp. Read this before contributing code.

---

## What gapp Does

gapp is a CLI tool that deploys Python MCP servers to Google Cloud Run with Terraform. A developer adds a `gapp.yaml` to their repo and runs four commands:

```
gapp init                    # scaffold gapp.yaml + Dockerfile, register locally
gapp setup <project-id>      # enable GCP APIs, create state bucket, label project
gapp secret set <name>       # populate secrets in Secret Manager
gapp deploy                  # build container, terraform apply
```

## Design Goals

**Remote MCP Access.** Every MCP server that accesses non-local resources (APIs, cloud data, third-party services) should be easily deployable to Cloud Run.

**Minimal Cognitive Load.** Adding a new MCP server to GCP should require near-zero configuration. The CLI always tells the user what step comes next.

**Resilient and Recoverable.** It should always be possible to tear down and rebuild. The system makes external dependencies, secret sources, and recovery paths clear.

**Solutions Are Independent.** Solutions in the same GCP project co-exist without knowing about each other. Each has its own TF state, secrets, and Cloud Run services.

## Architecture

### Where Things Live

```
GAPP REPO (this repo — defines HOW to deploy)
  terraform/main.tf                     ← static HCL, references shared module
  terraform/variables.tf                ← variable declarations
  modules/cloud-run-service/            ← reusable TF module
  gapp/sdk/deploy.py                    ← orchestrates build + TF apply

SOLUTION REPO (what gets deployed)
  gapp.yaml                             ← solution metadata, prerequisites
  Dockerfile                            ← static, uses ARG ENTRYPOINT (created by gapp init)

GCP (runtime state)
  Project labels: gapp-{name}=default   ← links project to solution
  Secret Manager: prerequisite values   ← credentials
  Cloud Run: running services           ← runtime
  GCS: gapp-{name}-{project-id}/       ← per-solution bucket (TF state)
  Cloud Build: container image builds   ← no local Docker needed
  Artifact Registry: gapp/ repo         ← container images

LOCAL (~/.config/gapp/, working cache, fully reconstructable)
  solutions.yaml                        ← name → project_id + repo_path
  ~/.cache/gapp/{solution}/terraform/   ← staged TF files + generated tfvars.json
```

### Convention Over Configuration

Most values are derived, not configured:

| Field | Convention | Override needed? |
|-------|-----------|-----------------|
| Solution name | Git repo directory name | Rarely (configurable in gapp.yaml) |
| Solution bucket | `gapp-{name}-{project-id}` | Never |
| TF state path | `terraform/state/` in solution bucket | Never |
| TF location | Static HCL in gapp repo, staged to `~/.cache/gapp/` | Never |
| Repo identity | Current working directory (git root) | Always use cwd |
| Image tag | HEAD commit SHA (12 chars) | Never |

### The 1:1:1 Default

One repo = one solution = one Cloud Run service. Multi-service solutions are supported but are the exception, not the organizing principle.

## Solution Lifecycle Phases

| Phase | What | Command |
|-------|------|---------|
| **Foundation** | GCP project exists, APIs enabled, bucket exists, project labeled | `gapp setup <project-id>` |
| **Prerequisites** | Secrets populated in Secret Manager | `gapp secret set <name>` |
| **Application** | Cloud Run service deployed via Terraform | `gapp deploy` |

Each phase completes cleanly and tells the user what comes next. No phase does double duty.

## The `gapp.yaml` File

Each solution repo has a manifest at the root:

```yaml
service:
  entrypoint: myapp.mcp.server:mcp_app   # REQUIRED: uvicorn module:app

prerequisites:
  secrets:
    api-token:
      description: "API authentication token"
```

Key decisions:
- **`service.entrypoint` is required** — passed as `--build-arg` to the static Dockerfile.
- **Port 8080 is hardcoded** — not configurable. All Cloud Run services use 8080.
- **No `prerequisites.apis`** — foundation APIs are hardcoded in `gapp setup`.
- **Secrets use kebab-case** — gapp auto-derives the UPPER_SNAKE env var name (`api-token` → `API_TOKEN`).

Optional overrides with defaults:

```yaml
service:
  entrypoint: app.mcp.server:mcp_app   # REQUIRED
  memory: "512Mi"                       # default
  cpu: "1"                              # default
  max_instances: 1                      # default
  public: false                         # default
  env:                                  # default: {}
    DB_HOST: "localhost"
```

## Static Terraform + Generated tfvars.json

Solutions never own Terraform files. gapp manages TF:

- **Static HCL** lives in this repo at `terraform/main.tf` and `terraform/variables.tf`.
- **Reusable TF module** at `modules/cloud-run-service/` handles Cloud Run v2 service, service account, IAM, env vars, and secret references.
- **At deploy time**, gapp stages TF files to `~/.cache/gapp/{solution}/terraform/`, generates only `terraform.tfvars.json`, and runs `terraform init + apply`.

This pattern follows a proven static TF + staging + tfvars.json approach.

### Why Solutions Don't Own TF

TF files are nearly identical boilerplate across solutions. Centralizing TF in gapp means:
- No drift between solution repos
- Framework upgrades benefit all solutions automatically
- Less cognitive load for simple MCP servers

## Container Build Pipeline

### Static Dockerfile with Build Args

Each solution repo has a static Dockerfile (created by `gapp init`) that uses `ARG ENTRYPOINT` to parameterize the uvicorn command. The Dockerfile is committed to the repo — no generation at build time.

### Source Integrity via `git archive`

Build source is piped from `git archive HEAD` directly into Cloud Build. This ensures the built image contains exactly the committed contents of HEAD — no uncommitted changes, no gitignored files, no working directory artifacts. The HEAD SHA is used as the image tag, making the tag truthful by construction.

### Dirty Tree Guard

`gapp deploy` blocks if the working tree has uncommitted changes. The user must commit or stash before deploying.

### Redundant Build Skipping

Before building, gapp checks if `{image}:{sha}` already exists in Artifact Registry. If it does, the build is skipped entirely. This makes re-deploys fast and free.

### Identity Consistency

A single identity is used across the entire deploy flow. gapp passes a gcloud access token to Terraform via the `GOOGLE_OAUTH_ACCESS_TOKEN` env var, ensuring gcloud CLI and Terraform use the same identity.

## Secrets Security Model

Secret values live in GCP Secret Manager within the project where they're consumed. Key properties:
- **Blast radius isolation** — per-project Secret Manager with its own IAM
- **No secret values in repos** — only secret names (references)
- **Secrets use kebab-case names** in `gapp.yaml` (e.g., `api-token`), auto-mapped to UPPER_SNAKE env vars on Cloud Run

## Code Architecture

### SDK Layer First

All business logic lives in `gapp/sdk/`. CLI and MCP layers are thin wrappers.

```
gapp/
├── sdk/           # business logic, testable, reusable
│   ├── config.py  # XDG-compliant config management
│   ├── context.py # solution detection and resolution
│   ├── deploy.py  # build + terraform orchestration
│   ├── init.py    # solution initialization
│   ├── manifest.py # gapp.yaml parsing
│   ├── secrets.py # Secret Manager operations
│   ├── setup.py   # GCP foundation provisioning
│   └── solutions.py # solution listing and discovery
├── cli/           # thin Click wrapper
│   └── main.py
```

If you're writing logic in a CLI command, stop and move it to SDK.

### Testing Standards

**Sociable unit tests.** No mocks unless testing network I/O. Isolate via temp dirs and env vars.

- **Unit tests (`tests/unit/`):** Fast, local, no network, no credentials. Subprocess only to ubiquitous tools (e.g., `git init`).
- **Integration tests (`tests/integration/`):** Only when explicitly requested. Excluded from default `pytest` run.

Test names describe scenario + outcome, not implementation:
- Good: `test_init_creates_manifest_and_dockerfile`
- Bad: `test_returns_false_when_file_missing`

Run tests: `python -m pytest tests/unit/ -v`

## Design Principles

### 1. Separate the Tool from the Deployment

**This repo is the tool** — application code, Dockerfile, and `gapp.yaml` live in solution repos. **GCP is the deployment** — project labels, Secret Manager, Cloud Run. **Local machine is ephemeral** — `~/.config/gapp/` is a reconstructable cache.

These tiers must not bleed: no project IDs in public repos, no credential values in any repo, no state that can't be reconstructed from GitHub + GCP.

### 2. Terraform Earns Its Keep

Even simple deployments involve 5-6 interdependent resources (service + SA + IAM + secret refs). Terraform manages the resource graph declaratively. The reusable patterns belong in shared modules; the app-specific configuration belongs in `gapp.yaml`.

### 3. Open/Closed Principle

Adding a solution = adding `gapp.yaml` + Dockerfile to a repo. No editing of existing gapp code or config files.

### 4. Prove Patterns Before Abstracting

Don't build abstractions until you've done the thing manually 2-3 times and felt the actual pain of repetition.

### 5. Config Is a List, Not a Graph

Solutions have no inter-service deployment dependencies. Each is independently deployable.

### 6. Visibility Is a Feature

GitHub topics (`gapp-solution`) enable discovery. `gapp solutions list` is the live inventory. Every system has one obvious entry point.

### 7. Derive, Don't Configure

If a value can be derived from convention, don't require configuration. The only truly unique input is the GCP project ID.

### 8. The CLI Always Knows What's Next

Every status display, error message, and blocking condition ends with the specific next action to take.

### 9. Solutions Are Independent

Solutions in the same project co-exist without knowing about each other. Each has its own TF state, secrets, and services. If two solutions need to communicate, they should be one solution.

### 10. Secrets Stay Decentralized

Secret values live in GCP Secret Manager per-project. No central vault, no secret values in repos. Recovery procedures are documented per-secret in `gapp.yaml`.
