# Security

## Reporting a vulnerability

Please do not report security vulnerabilities through public GitHub issues.

Email the maintainers directly (see repository contact info) or open a private
security advisory via GitHub's **Security → Advisories** tab.

Include:
- Description of the issue
- Steps to reproduce
- Affected version (git hash or tag)
- Potential impact

We will acknowledge reports within 72 hours and aim to resolve confirmed
vulnerabilities within 14 days.

---

## Known security boundaries

Smriti is a single-user tool with no authentication layer. It is designed for
local or private-network deployment.

**Do not expose the backend port (8000) to the public internet.** The API has no
authentication; anyone who can reach it can read and write all data.

If you deploy Smriti on a server:

- Put the backend behind a reverse proxy (nginx, Caddy, etc.)
- Restrict access with network-level controls or auth middleware
- Change the default database credentials in `docker-compose.yml` and `.env`
- Do not commit `backend/config/providers.yaml` — it is gitignored for this reason

---

## API keys

API keys are configured via environment variables or `backend/config/providers.yaml`
(gitignored). They are never returned by any API endpoint. The backend logging
middleware applies a `SecretGuardFilter` that redacts `sk-*` patterns from all log
output.
