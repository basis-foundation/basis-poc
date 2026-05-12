# ADR-0008 — No Kubernetes Dependency

**Status:** Accepted  
**Date:** 2025-01-01  

## Context

Kubernetes has become the default deployment target for many containerized applications. It offers genuine capabilities: workload scheduling, horizontal scaling, rolling updates, service discovery, and a rich ecosystem of operators and tooling. For organizations already running a Kubernetes cluster, deploying into it is often the path of least resistance.

BASIS is not designed for organizations already running Kubernetes. It is designed for operational technology environments where:

- The operator is a building automation engineer, a facilities manager, or a small IT team — not a platform engineer with Kubernetes expertise.
- The deployment target may be a single physical server, an industrial PC, or a ruggedized edge appliance. Running Kubernetes on a single node is possible, but it adds substantial complexity (etcd, the control plane, kubelet, CNI) for no operational benefit.
- Network policies, RBAC, and pod security contexts in Kubernetes are a separate security model that must be maintained alongside the application-level security model BASIS implements. This layering creates operational complexity without improving the security posture in a single-host deployment.
- Kubernetes requires persistent internet connectivity for image pulls, certificate rotation (cert-manager), and cloud provider integrations unless a fully air-gapped cluster is constructed — which is a significant operational undertaking in its own right.
- Many OT environments prohibit or restrict the software that can be installed on control network systems. Kubernetes requires kernel features (cgroups, namespaces, eBPF) that may not be approved by the site's change control process.

The risk of introducing a Kubernetes dependency is not hypothetical. Several open-source security tools have followed the path of adding Kubernetes support and, over time, implicitly made it the primary deployment model. Documentation for bare-metal or Docker Compose deployment atrophied. The operational complexity of the tool increased. Adoption in resource-constrained environments declined.

## Decision

BASIS requires Docker and Docker Compose. It does not require Kubernetes. This is a deliberate constraint, not a limitation to be resolved in a future stage.

The compose stack is the deployment unit. `docker compose up` is the deployment command. Configuration is via environment variables documented in `.env.example`. Persistent state lives in named Docker volumes. There is no Helm chart, no Kubernetes operator, no admission webhook, and no dependency on cluster-level infrastructure.

This decision does not prevent someone from deploying BASIS on Kubernetes — the containers are standard images and would run in pods without modification. It means BASIS will not be designed, documented, or tested with Kubernetes as the assumed deployment environment. Kubernetes-specific configuration (Helm charts, Kustomize overlays, Kubernetes Secrets mappings) is out of scope for the core project.

## Consequences

**Accepted trade-offs:**
- Docker Compose does not provide native high availability, rolling updates, or workload scheduling. Organizations that require these capabilities for their BASIS deployment must implement their own approach — Docker Swarm, a reverse proxy for rolling restarts, or indeed Kubernetes.
- The compose stack is a single-host deployment by default. Horizontal scaling requires external coordination that the project does not provide.

**Benefits realized:**
- The deployment prerequisite is Docker, which is available on every major operating system, runs on ARM and x86, and is installable without cluster infrastructure.
- The operational model is familiar to a much broader audience than Kubernetes. A facilities engineer who has never managed a Kubernetes cluster can deploy and operate BASIS.
- Consistent with [ADR-0006](ADR-0006-local-first-architecture.md): no dependency on cluster infrastructure means no dependency on cloud provider integrations, managed control planes, or external DNS/certificate authorities.
- The project remains approachable as an open-source contribution target. Contributors can run the full stack locally without a multi-node cluster or a cloud account.
- Debugging is straightforward: `docker compose logs`, `docker compose exec`, and `docker compose ps` provide complete observability without cluster-level tooling.
