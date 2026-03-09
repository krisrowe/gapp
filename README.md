# gapp — GCP App Deployer

CLI tool for deploying Cloud Run services with Terraform.

## Overview

gapp provides a four-step workflow for deploying applications to GCP:

```
gapp init         # Initialize current repo as a gapp solution (local only)
gapp setup <id>   # GCP foundation: enable APIs, create bucket, label project
gapp secret set   # Set prerequisite secrets in Secret Manager
gapp deploy       # Build container + terraform apply
```

Each step is idempotent and can be re-run safely.

## Additional Commands

```
gapp status [name]              # Full health check across all phases
gapp plan                       # Terraform plan (preview changes)
gapp solutions list [--available]  # List local (and GitHub) solutions
gapp solutions restore <name>   # Clone from GitHub + find GCP project
gapp secret list                # Show prerequisite secrets and status
```

## Key Concepts

- **Solution**: A repo with a `deploy/manifest.yaml` that describes what to deploy.
- **Per-solution GCS bucket**: `gapp-{name}-{project-id}` stores Terraform state and solution data.
- **GCP project labels**: `gapp-{name}=default` enables auto-discovery of existing projects.
- **GitHub topic**: `gapp-solution` enables repo discovery via `gapp solutions list --available`.

## Installation

```bash
pip install -e .
# or
pipx install .
```

## Development

```bash
pip install -e ".[dev]"
pytest
```

## MCP Server

Not yet implemented. Will provide the same SDK functionality as the CLI for AI agent access.
