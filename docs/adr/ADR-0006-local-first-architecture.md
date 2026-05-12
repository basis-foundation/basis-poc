# ADR-0006 — Local-First Architecture Philosophy

**Status:** Accepted  
**Date:** 2025-01-01  

## Context

Building automation and operational technology systems present a specific deployment reality that is often invisible to developers who work primarily in cloud-connected environments:

- Many OT environments are air-gapped by design. The control network is physically isolated from corporate IT networks and from the internet. This isolation is a security control, not an oversight.
- Internet connectivity cannot be assumed on the control path. A fire suppression system, HVAC controller, or physical access system must function when the internet is unavailable, when a cloud provider has an outage, or when network maintenance is in progress.
- Operators in these environments are often not cloud infrastructure specialists. A deployment that requires configuring cloud IAM policies, managing TLS certificates against a public CA, or understanding VPC networking is a deployment that will not be adopted.
- Audit and security records for OT systems may be subject to data residency requirements. Transmitting authorization decisions and command records to an external service introduces compliance surface that many operators want to avoid.

Modern software architecture defaults have drifted toward assuming cloud connectivity: managed databases, external identity providers, centralized logging platforms, secrets managers. These defaults are reasonable for cloud-native applications. They are problematic for a platform targeting OT environments.

## Decision

Every component of BASIS must be operable without any external network dependency. The full platform — identity provider, message broker, API, frontend, OT simulator — runs in a single `docker compose up` on a single host with no internet access after initial image pull.

This constraint shapes specific decisions throughout the codebase:

- **Identity provider is self-hosted.** Keycloak runs as a container in the compose stack. There is no dependency on a cloud OAuth2 provider (Auth0, Okta, AWS Cognito). Realm configuration is imported from a local file at startup.
- **Message broker is self-hosted.** Mosquitto runs as a container. There is no cloud MQTT service dependency.
- **Audit persistence is local.** SQLite writes to a named Docker volume. There is no dependency on a database service, log aggregation platform, or cloud storage bucket. See [ADR-0002](ADR-0002-sqlite-audit-persistence.md).
- **No secrets manager dependency.** Credentials are passed via environment variables and Docker secrets. The compose stack includes an `.env.example` that documents every required variable.
- **No container registry dependency at runtime.** Base images are standard public images (Python, Keycloak, Mosquitto, Node). They can be pulled once, saved with `docker save`, and distributed offline if required.

"Local-first" does not mean "cloud-incompatible." A deployment with an externally hosted Keycloak instance, a managed MQTT broker, or a PostgreSQL audit store is achievable by replacing individual components. The default configuration requires none of these. Extensions are opt-in, not opt-out.

## Consequences

**Accepted trade-offs:**
- Self-hosted Keycloak requires the operator to manage realm configuration, user accounts, and credential rotation. A managed identity provider offloads this operational burden but introduces a network dependency on the control path.
- SQLite is not appropriate for multi-host deployments where audit writes originate from multiple API instances. This is a known limitation documented in [ADR-0002](ADR-0002-sqlite-audit-persistence.md).
- Local-first deployment means there is no built-in high availability. A single-host failure takes down the entire stack. This is appropriate for a PoC and for small-to-medium OT deployments; it is not appropriate for critical infrastructure without an explicit HA architecture.

**Benefits realized:**
- The platform is demonstrable in environments with no internet access. This is a hard requirement for many OT contexts, not a nice-to-have.
- Data sovereignty is straightforward. Audit records, identity data, and operational telemetry never leave the host without explicit operator action.
- Operational dependencies are enumerated and bounded. There are no implicit dependencies on external services that could degrade or fail silently.
- Setup is reproducible. Anyone with Docker and the repository can run the full platform in under five minutes with no account creation, no API keys, and no cloud configuration.
