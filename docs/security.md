# Security notes

## Trust boundaries

The submission treats all client input and all upstream provider output as untrusted.

### MCP gateway

- Caller identity is derived from a verified bearer JWT, never from JSON-RPC parameters.
- Only `admin` and `viewer` are accepted roles.
- `admin_*` tool policy is checked before forwarding.
- Blocked requests return the required JSON-RPC error and never reach downstream.
- JWT expiry is required.
- The checked-in JWT secret is a development fallback only. Real deployment must inject a secret or verify asymmetric tokens from an identity provider.

### MCP server

- Pydantic models use strict mode and reject extra fields.
- Invalid input returns protocol-level `-32602` errors.
- Protocol errors include field location/type/message but do not echo raw submitted values.
- Logging is configured to stderr for stdio isolation.

### Streaming guardrail

- Sensitive output is redacted before emission to the client.
- Potential PII suffixes are retained until they can be classified safely.
- Carry memory is bounded.
- Credit card candidates require a valid Luhn checksum before redaction.
- Upstream exceptions are not streamed verbatim to the user.

### Model router

- Tenant identity comes from `X-API-Key`.
- SQLite stores a SHA-256 tenant identifier rather than the raw API key credential.
- Token capacity is reserved atomically before upstream execution.
- SQLite transactions serialize competing reservations.
- Raw provider stack traces, bodies, and exceptions are never returned to clients.
- Primary timeouts are cancelled before fallback begins.
- Only 429 and timeout trigger fallback, avoiding automatic replay of arbitrary bad requests.

## What is intentionally not claimed

This assessment implementation is not a complete production identity, PCI, HIPAA, or compliance system. In production, additional controls would include TLS/mTLS, key rotation, centralized secrets, provider-specific tokenization, audit retention, distributed rate-limit state, and formal PII classification policy.
