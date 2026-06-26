# sample-ops-dashboard Architecture

## Overview
Sample Ops Dashboard is a small public-safe operations dashboard that tracks build health, service status, and incident review notes for a demo engineering team.

## Components
### Application Code
- src (directory): Primary application source code.

### Runtime Services
- web (container): Container service declared in Compose configuration.
- redis (container): Container service declared in Compose configuration.

### Data Stores
- Redis (data_store): Detected from project configuration or source references.

### Deployment Signals
- Compose (container): docker-compose.yml
- GitHub Actions (ci): .github/workflows/ci.yml

## Entry Points
- main: src/main.ts

## Scan Coverage
No scan skips were recorded.

