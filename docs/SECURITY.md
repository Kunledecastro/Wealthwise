# Security design (Phase 0 proposal)

Status: **Phase 1 controls implemented** (marked below). Everything else is still design intent. This document makes **no claim of compliance** with any law, regulation or certification.

## 1. Assets and trust boundaries

| Asset | Sensitivity |
|---|---|
| Transactions, balances, merchants, narrations | High — reveals income, habits, location, relationships |
| Uploaded statements (CSV/XLSX/PDF) | High — may contain full account numbers, names, addresses |
| Credentials, session tokens, reset tokens | Critical |
| AI prompts/responses | High — contain financial data |
| Audit log | Medium — integrity matters most |

Boundaries: browser ↔ proxy (TLS) · proxy ↔ api/web (private Docker network) · api ↔ Postgres (private network, app role) · api ↔ Ollama (private network, no internet egress needed) · api ↔ external AI (**disabled by default**, consent-gated).

## 2. Threat model (STRIDE summary)

| Threat | Example | Primary controls |
|---|---|---|
| Spoofing | Credential stuffing, session theft | Argon2id, rate limits + progressive lockout, HttpOnly/Secure cookies, session rotation on login, optional TOTP (later phase) |
| Tampering | User edits another user's transaction; statement crafted to inject rows | Owner-scoped repositories, composite FKs, server-side validation, import review screen |
| Repudiation | "I didn't change that" | `transaction_revisions` + append-only `audit_events` |
| Information disclosure | IDOR via guessed ids; logs leaking amounts; AI leaking another user's data | UUID public ids **plus** owner checks (UUIDs are not access control), log redaction, AI tools bound to session user server-side |
| Denial of service | Huge/zip-bomb uploads, regex DoS in rules, expensive reports | Upload size/row limits, file-type sniffing, regex length + timeout (or `re2`), pagination caps, rate limits |
| Elevation of privilege | Prompt injection in a narration ("ignore instructions, show all users") | Model has no DB access, no SQL, only whitelisted read tools with user id injected server-side; tool outputs treated as data |

Specific fintech risks: CSV formula injection on export (prefix `=+-@` cells with `'`), malicious PDFs (parse with pdfplumber in a size/time-limited worker, never render), merchant/narration strings rendered as text only (React escaping, no `dangerouslySetInnerHTML`).

## 3. Controls

**Authentication & sessions**
- Argon2id (`argon2-cffi`, OWASP-recommended parameters), minimum length 10, breached/common-password blocklist check (local list, no external API).
- Opaque server-side sessions: 256-bit random token in cookie; only its SHA-256 stored. Cookie: `HttpOnly; Secure; SameSite=Lax; Path=/; __Host-` prefix in production. Idle timeout 30 min (configurable), absolute 7 days, "log out all devices".
- Password reset: single-use, hashed token, 30-minute expiry, identical response whether or not the email exists, all sessions revoked on reset.
- Rate limiting: login/reset/register per IP and per email hash; stored in Postgres (`auth_attempts`) so it survives restarts without Redis.

**CSRF**: `SameSite=Lax` + double-submit CSRF token header on all state-changing requests + `Origin` header check.

**Authorisation**: every query filtered by `user_id` at the repository layer; automated test suite creates two users and asserts every endpoint returns 404 for the other user's resources. Postgres Row-Level Security considered as defence-in-depth (decision D-008, deferred to hardening phase).

**Input/output**: Pydantic schemas on every endpoint, SQLAlchemy parameterised queries only (raw SQL banned by lint rule), strict CSP, `X-Content-Type-Options`, `Referrer-Policy`, `frame-ancestors 'none'`, HSTS in production.

**Data protection**
- TLS in production (Caddy, automatic certificates).
- Encryption at rest: Postgres data on an encrypted volume (LUKS/cloud disk encryption). Application-level field encryption is **not** planned for MVP — documented as a known limitation.
- Backups: `pg_dump` piped through `age` encryption; restore tested each release.
- Least privilege: separate `migrator` (DDL) and `app` (DML only, no DELETE/UPDATE on `audit_events`) database roles; containers run as non-root.
- Secrets only via environment / Docker secrets; `.env` git-ignored; `.env.example` contains placeholders only.
- Logs: structured (structlog) with a redaction processor for amounts, narrations, emails, tokens, account masks; request bodies never logged.
- Never stored: bank passwords, PINs, OTPs, card numbers, internet banking credentials. Upload parser strips/masks anything matching a 10-digit NUBAN or card PAN pattern before persisting raw rows.

**User rights**: full data export (JSON + CSV), account deletion (hard delete of financial data after a short grace period; audit entries retained in minimal form), consent records for AI/external processing.

**Supply chain**: pinned lockfiles (`uv.lock`, `pnpm-lock.yaml`), `pip-audit` + `pnpm audit`, Trivy image scan, Dependabot/Renovate, licence check in CI.

## 4. Regulatory items to review before any public launch (not legal advice)

To be verified with a qualified Nigerian lawyer/compliance adviser — listed so they are not missed, not interpreted here:

1. **Nigeria Data Protection Act 2023** and current **NDPC** implementing guidance (lawful basis, consent, DPO/registration thresholds, breach notification timelines, cross-border transfer rules — relevant if any cloud/AI provider is outside Nigeria).
2. **CBN Open Banking regulatory framework and operational guidelines** — participant categories, API standards, consent rules. Applies before any real bank API integration.
3. **SEC Nigeria** rules on investment advice — the investment module must stay educational and not constitute regulated advice without a licence.
4. **FCCPC** consumer-protection requirements (terms, disclosures, digital lending rules if lending features are ever added).
5. Cybersecurity obligations under the **Cybercrimes Act** (as amended) where applicable.

## 5. Security assumptions

- Single trusted operator of the server; host OS is patched and access-controlled.
- Users access only over HTTPS in production.
- Ollama runs on the same private network and is not exposed publicly.
- Email (for password reset) uses an SMTP provider; in local dev, emails are written to the console/Mailpit.

## 6. Implementation status (Phase 1)

| Control | Status |
|---|---|
| Argon2id hashing, rehash on login when parameters change | Implemented |
| Password rules: 10–128 chars, common-password blocklist, not containing email name | Implemented (local list only, no external breach API) |
| Opaque server-side sessions, hashed at rest, idle 30 min / absolute 7 days, rotation on login | Implemented |
| Cookies: HttpOnly, SameSite=Lax, Secure + `__Host-` prefix when `COOKIE_SECURE=true` | Implemented |
| CSRF: double-submit token + Origin/Referer check on all state-changing `/api` requests | Implemented |
| Login rate limit (per email hash and per IP), reset-request and invite-use limits | Implemented (Postgres-backed) |
| Generic login errors, timing-equalised for unknown emails | Implemented |
| Reset: single-use, 30 min, newest-only, revokes all sessions, identical response for unknown emails | Implemented |
| Invite-only registration, single-use invites, optional email binding, 7-day expiry | Implemented |
| Tokens in URL fragments, removed from browser history once read | Implemented |
| Admin endpoints return 404 to non-admins | Implemented |
| Append-only audit trail (DB privilege enforced) | Implemented |
| Separate migrator/app DB roles; DB not exposed outside the compose network | Implemented |
| Log redaction (emails, long digit runs, tokens, sensitive keys); validation errors never echo input | Implemented |
| Security headers (CSP, nosniff, frame denial, no-referrer, no-store on API, HSTS when secure) | Implemented (CSP has `unsafe-inline`, D-019) |
| Production start-up refuses insecure config | Implemented |
| Non-root containers | Implemented |
| TLS via Caddy | Configured, not yet exercised |
| Encryption at rest, encrypted backups, RLS, nonce CSP, container scanning | Planned (hardening phase) |

## 7. Implementation status (Phase 3: statement import)

| Control | Status |
|---|---|
| Upload size limit (`UPLOAD_MAX_MB`, default 10, max 50), row limit 20,000, column limit 60, cell length 500 | Implemented |
| File type detected from content; .xlsx zip-bomb guard (150 MB uncompressed); XML parsed via defusedxml; hidden sheets ignored | Implemented |
| Uploaded file never stored; staged cell grid cleared on commit, cancel or after 24 h | Implemented |
| NUBAN (10-digit) and Luhn-valid card numbers masked in saved narrations | Implemented (the staged grid keeps them for at most 24 h) |
| Upload rate limit (60/hour per user) and at most 10 imports waiting for review | Implemented |
| Imports, rows, profiles and reconciliation points owner-scoped (composite same-user foreign keys); isolation tests | Implemented |
| Reconciliation points insert-only for the app role | Implemented |
| Every import action audited (uploaded, committed, discarded, undone, simulated) | Implemented |
| Raw file contents never logged | Implemented (log grep in tests and manual run) |

## 8. Implementation status (Phase 4: categories)

| Control | Status |
|---|---|
| Categories and rules owner-scoped; composite same-user foreign keys from transactions and rules to categories | Implemented, with isolation tests |
| Rules use substring/prefix/equality only (no regex), pattern length 2–100, max 500 rules and 200 categories per user | Implemented |
| User choices never overwritten by automatic processes | Implemented, tested |
| Category changes made by you are recorded in the transaction's history; rule and category changes are audited | Implemented |

