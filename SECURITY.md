# Security Policy

## Scope

This repository is a **proof-of-concept** for an OT identity and authorization control plane. It is not a production system and is not deployed in any production environment by the maintainers.

Security reports are still welcome — particularly those that identify:

- Vulnerabilities in the identity or authorization model (JWT validation, role enforcement, PKCE flow)
- Logic flaws in the command dispatch or audit path
- Credential exposure patterns in the default configuration
- Dependency vulnerabilities with a realistic attack path in the PoC context

Issues that are already documented as known limitations (WebSocket unauthenticated, no TLS, Keycloak in dev-file mode) are noted in the README and do not need to be reported separately.

---

## Reporting a Vulnerability

**Please do not open a public GitHub issue for security vulnerabilities.** Public issues disclose the vulnerability before a fix is available.

To report a vulnerability privately:

1. Use GitHub's [private vulnerability reporting](https://docs.github.com/en/code-security/security-advisories/guidance-on-reporting-and-writing/privately-reporting-a-security-vulnerability) feature (Security → Report a vulnerability on this repository).
2. Alternatively, email the maintainer directly. Contact information is available on the GitHub profile associated with this repository.

Include in your report:

- A description of the vulnerability and its potential impact
- Steps to reproduce, or a minimal proof-of-concept
- Which component(s) are affected (API, Keycloak config, MQTT, frontend, Docker setup)
- Any suggested remediation if you have one

---

## Response Expectations

This is a volunteer-maintained open-source project. You can expect:

- An acknowledgement within **7 days** of a private report
- A status update (confirmed, investigating, or declined) within **21 days**
- A fix or public advisory within **90 days** for confirmed vulnerabilities, coordinated with you where possible

If you do not receive an acknowledgement within 7 days, follow up on the original report thread.

---

## Disclosure Policy

The maintainers follow **coordinated disclosure**:

- Vulnerabilities are fixed before public disclosure wherever practical.
- Credit is given to reporters in the release notes or advisory unless anonymity is requested.
- There is no bug bounty program for this project.

---

## Development Credentials in This Repository

This repository intentionally includes development-only credentials to allow `docker compose up` to work without any configuration:

| Credential | Location | Notes |
|---|---|---|
| `admin` / `admin` | `.env.example` → Keycloak | Keycloak admin UI only, dev environment |
| `demo123` | `infra/keycloak/realm-export.json` | Demo user passwords, dev environment |
| `basis-api-secret` | `.env.example`, `docker-compose.yml` defaults | MQTT service credential, dev environment |
| `basis-simulator-secret` | `.env.example`, `docker-compose.yml` defaults | MQTT service credential, dev environment |
| Hashed credentials | `infra/mosquitto/passwd` | PBKDF2-SHA512 hashes of the above |

None of these credentials are used in any production deployment by the maintainers. They are explicitly development values and should be replaced before deploying to any shared environment. This is documented in `.env.example`.

These are **not** vulnerability reports — they are documented design decisions for a local-development PoC.
