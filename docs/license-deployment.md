# EKONT SMART REPORT — License Deployment Guide

How commercial licenses are generated (vendor side) and deployed on a customer
backend (operator side). Audience: the EKONT release/deployment team.

---

## 1. Model

Licensing uses **asymmetric JWT signing**:

- The **vendor** holds a PRIVATE key and signs a license token (`license.jwt`)
  with it. The private key is the only thing that can mint a license.
- The **customer backend** holds the matching PUBLIC key and verifies the token
  at startup. The public key cannot create or alter licenses.

```
 vendor (offline, secret)                 customer backend (on-prem)
 ┌───────────────────────┐                ┌────────────────────────────┐
 │ private key  ──sign──▶ license.jwt ──▶ │ public key ──verify── start │
 │ claims:               │   (ship)       │ enforce max_tags / features │
 │  product, customer,   │                │ reject if expired/invalid   │
 │  features, max_tags,  │                └────────────────────────────┘
 │  exp                   │
 └───────────────────────┘
```

Verification runs **once at startup** (`app.core.license.verify_required_license`).
A missing, expired, tampered, or wrong-product token makes the backend **refuse to
start** (fail-closed). Default is **disabled** — development and tests are
unaffected unless `SCADA_LICENSE_REQUIRED=true`.

---

## 2. Vendor: one-time key generation

Run with the backend venv (it has `jose` + `cryptography`):

```bash
cd scada-reporter/backend
.venv/Scripts/python ../../scripts/generate_license.py keygen --type rsa --name ekont
# or:  just license "keygen --type rsa --name ekont"
```

Produces:

| File | Distribution |
|------|--------------|
| `ekont_private.pem` | **SECRET** — keep offline (password manager / HSM / vault). Never ship. |
| `ekont_public.pem`  | Ships to every customer (goes into their env). |

Key type:

- `--type rsa` → sign with `RS256` (default, widely compatible).
- `--type ec` → sign with `ES256` (smaller keys/tokens).

Generate the keypair **once** and reuse it for all customers. Rotating the
private key invalidates every issued license (see §7).

---

## 3. Vendor: issue a license

```bash
cd scada-reporter/backend
.venv/Scripts/python ../../scripts/generate_license.py issue \
  --private-key ekont_private.pem --algorithm RS256 \
  --customer "ACME Su A.Ş." --license-id lic_2026_001 \
  --features advanced_reports,grafana,realtime,export \
  --max-tags 500 --days 365 \
  --out license.jwt --public-key ekont_public.pem
```

`--public-key` is optional but recommended: the tool **self-verifies** the freshly
minted token against that public key before writing it, catching key/algorithm
mismatches before the customer does. The command also prints the exact deploy env
block to copy.

### Claims reference

| Flag | Claim | Meaning |
|------|-------|---------|
| `--customer` (required) | `customer` | Customer name, shown in the startup log. |
| `--license-id` | `license_id` | Serial / order reference. |
| `--product` | `product` | Must match the backend's `SCADA_LICENSE_PRODUCT` (default `ekont-smart-report`). |
| `--features` | `features` | Comma-separated allow-list. **Empty = full version** (all gates open). |
| `--max-tags` | `max_tags` | Tag cap. **Omit = unlimited.** |
| `--days N` / `--expires <unix>` | `exp` | Expiry. **Omit = perpetual** (never expires). |

### Feature keys

`--features` accepts these keys; each gates a capability. A key absent from a
**non-empty** list returns HTTP 403 on those endpoints.

| Feature key | Gated capability |
|-------------|------------------|
| `advanced_reports` | `/api/advanced-reports/*` — report templates, scheduling, archive. |
| `grafana` | Grafana watchlist-group sync (`/api/dashboard/watchlist-groups/sync-grafana`). |
| `realtime` | SSE live streams (`/api/dashboard/stream`, `/api/dashboard/logs/stream`). |
| `export` | Tag export (`/api/tags/export`, CSV/XLSX). |

> Empty `features` (omit `--features`) = **full version**: every gate is open.
> A non-empty list is a strict allow-list — list every feature the customer buys.

---

## 4. Operator: deploy on the customer backend

### 4.1 Place the license file

Copy `license.jwt` to the customer host, e.g.:

```
/etc/ekont-smart-report/license.jwt
```

Restrict read access to the service account (POSIX `chmod 600`, or NTFS ACL on
Windows).

### 4.2 Set environment variables

In the customer's `.env` (see `.env.production.example`):

```ini
# Commercial license verification
SCADA_LICENSE_REQUIRED=true
SCADA_LICENSE_FILE=/etc/ekont-smart-report/license.jwt
SCADA_LICENSE_PUBLIC_KEY="-----BEGIN PUBLIC KEY-----\n...\n-----END PUBLIC KEY-----"
SCADA_LICENSE_ALGORITHMS=RS256,ES256
SCADA_LICENSE_PRODUCT=ekont-smart-report
```

| Variable | Notes |
|----------|-------|
| `SCADA_LICENSE_REQUIRED` | `true` enables enforcement. Default `false`. |
| `SCADA_LICENSE_FILE` | Path to `license.jwt`. Accepts a raw JWT or a `{"license": "..."}` JSON wrapper. |
| `SCADA_LICENSE_TOKEN` | Alternative to the file: paste the token inline. The file is read only when the token is empty. |
| `SCADA_LICENSE_PUBLIC_KEY` | Contents of `*_public.pem`. **Escape newlines as `\n`** (env is single-line) — the backend un-escapes them. |
| `SCADA_LICENSE_ALGORITHMS` | Allowed signing algorithms. Keep the one you signed with; `none` is always rejected. |
| `SCADA_LICENSE_PRODUCT` | Must equal the token's `product` claim. |

Convert a PEM to a single-line `\n` value:

```bash
awk 'BEGIN{ORS="\\n"} {print}' ekont_public.pem
```

### 4.3 Restart and verify

Restart the backend service (e.g. `Restart-Service EkontBackend`, or `just
restart-backend` in dev). On success the log shows:

```
Commercial license verified: customer=ACME Su A.Ş. license_id=lic_2026_001
```

If verification fails the backend **does not start** and logs a config error —
the service stays down until the license/key is fixed.

---

## 5. Enforcement behavior

Once a valid license is active:

- **Tag quota (`max_tags`)** — enforced when creating tags: `POST /api/tags/`,
  `POST /api/tags/import`, `POST /api/tags/import_csv`. Adding tags past the cap
  returns **403**. Bulk imports are atomic: if the batch would exceed the cap,
  **nothing** is inserted. Omitted `max_tags` = unlimited.
- **Feature gates** — endpoints for un-licensed features return **403**. Empty
  `features` = all open.
- **Expiry (`exp`)** — an expired token fails verification → backend won't start.
  There is no runtime grace period; renew **before** expiry (see §6).

`SCADA_LICENSE_REQUIRED=false` (or no active license) means **unrestricted** —
full version, no quota, all gates open. Use this for evaluation/PoC.

---

## 6. Renewal and plan changes

Licenses are static tokens; to change limits, features, or expiry, **issue a new
token** with the same keypair and replace the file:

1. `issue` a new `license.jwt` with updated claims (new `--days`, `--max-tags`,
   `--features`).
2. Replace the file on the customer host.
3. Restart the backend.

The public key and env vars stay the same — only the file changes. Track issued
licenses (customer, `license_id`, expiry) in a vendor-side registry so renewals
are not missed.

---

## 7. Security

- **Private key is the crown jewel.** Anyone with it can mint unlimited
  licenses. Keep it offline; never commit it, never ship it, never put it in a
  customer image or `.env`.
- Keypairs and `license.jwt` are **not** tracked in git. Confirm `.gitignore`
  covers `*.pem` and `*.jwt` before generating into the repo tree, or generate
  into a directory outside the repo.
- Rotating the private key invalidates **all** existing licenses — only do it on
  compromise, and plan to re-issue every customer's license.
- The token is signed, not encrypted: claims (customer, limits) are readable.
  That is fine — integrity, not secrecy, is what matters here.
- `none` algorithm and unsigned tokens are rejected by both the signer and the
  verifier.

---

## 8. Troubleshooting

| Symptom | Cause | Fix |
|---------|-------|-----|
| Backend won't start, "License token signature or claims are invalid" | Public key doesn't match the signing private key, or wrong algorithm. | Use the `*_public.pem` paired with the signing key; set `SCADA_LICENSE_ALGORITHMS` to include the signing algo. |
| "License product mismatch" | Token `product` ≠ `SCADA_LICENSE_PRODUCT`. | Re-issue with matching `--product`, or align the env var. |
| "License file cannot be read" | Wrong `SCADA_LICENSE_FILE` path or permissions. | Fix the path; grant the service account read access. |
| Verification fails right after issuing | Token expired (`--days` in the past) or clock skew. | Re-issue with a future expiry; check host time/NTP. |
| Endpoints return 403 unexpectedly | Feature not in a non-empty `features` list. | Re-issue including the needed feature key, or issue with empty `features` for full version. |
| Tag create/import returns 403 | `max_tags` reached. | Re-issue with a higher `--max-tags`, or omit it for unlimited. |
| `SCADA_LICENSE_PUBLIC_KEY` parse errors | Newlines not escaped. | Store the PEM as one line with `\n` escapes (see §4.2). |

---

## 9. Reference

- Verifier: `scada-reporter/backend/app/core/license.py` (`verify_required_license`,
  `verify_license_token`).
- Signer / generator: `scripts/generate_license.py`, `build_license_token`.
- Startup wiring: `scada-reporter/backend/app/main.py` (lifespan).
- Enforcement: `scada-reporter/backend/app/api/license_guard.py`.
- Env template: `scada-reporter/backend/.env.production.example`.
