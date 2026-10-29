# QuilrAI AI Field Developer / Solutions Engineer Assessment

A runnable Python submission for the four assessment tasks covering MCP protocol handling, MCP gateway authorization, low-latency streaming PII guardrails, and resilient LLM model routing.

The implementation favors small, testable components and explicit failure behavior over unnecessary infrastructure. The repository is designed so a reviewer can install once, run one test command, and inspect each task independently.

## Quick start

Requirements:

- Python 3.11+
- Internet access for the initial dependency install

```bash
python -m venv .venv
source .venv/bin/activate       # Windows: .venv\\Scripts\\activate
python -m pip install -U pip
python -m pip install -e '.[dev]'
pytest
```

Optional linting:

```bash
ruff check src tests mocks scripts
```

## Repository map

```text
src/quilrai_assessment/
├── task1_mcp_server/          # Official MCP SDK stdio server
├── task2_security_gateway/    # JWT-authenticated MCP JSON-RPC reverse proxy
├── task3_stream_guardrail/    # Stateful streaming PII redaction gateway
└── task4_model_router/        # SQLite token limiter + primary/fallback router

tests/                         # Adversarial and concurrency tests
mocks/                         # Self-contained downstream MCP and LLM providers
docs/architecture.md           # Design diagrams and request flows
docs/security.md               # Security assumptions and threat controls
docs/evaluation-map.md         # Assessment rubric mapped to code and tests
```

## Task 1: Custom MCP server

### What it implements

- Official `mcp` Python SDK v2 API
- stdio transport
- `get_customer_record`
- `trigger_refund`
- strict Pydantic validation
- customer IDs matching `^CUST-\\d{5}$`
- positive, finite refund amounts
- refund reasons of at least 10 characters
- unknown input fields rejected
- validation errors mapped to JSON-RPC `-32602 Invalid params`
- application logs sent to stderr only

The server intentionally uses the official SDK's low-level `Server` API. The high-level decorator API normally turns schema validation failures into `isError=true` tool results. The assessment explicitly asks for standard JSON-RPC error codes, so this implementation performs Pydantic validation inside the official low-level tool handler and raises `MCPError(INVALID_PARAMS)` deliberately.

Run:

```bash
python -m quilrai_assessment.task1_mcp_server.server
```

The process waits for an MCP client over stdin/stdout. There is no HTTP port.

The integration test starts the server as a subprocess through the official MCP client. A successful handshake/list/call proves the stdio channel is not polluted by application output.

## Task 2: MCP security gateway

### Request flow

```text
AI agent
   |
   | Authorization: Bearer <JWT>
   v
MCP security gateway
   |
   +-- tools/list ----------------------------> downstream MCP
   |
   +-- tools/call normal_* -------------------> downstream MCP
   |
   +-- tools/call admin_*
          |
          +-- role=admin ----------------------> downstream MCP
          |
          +-- role=viewer --> JSON-RPC -32001
                              downstream calls = 0
```

JWTs contain a signed `role` claim (`admin` or `viewer`) plus `sub` and `exp`. The gateway does not trust a role supplied inside the JSON-RPC payload.

Run the mock downstream server:

```bash
make mock-mcp
```

In another terminal:

```bash
export JWT_SECRET='0123456789abcdef0123456789abcdef'
make task2
```

Generate development tokens:

```bash
JWT_SECRET='0123456789abcdef0123456789abcdef' make tokens
```

A viewer attempting `admin_reset_key` receives:

```json
{
  "jsonrpc": "2.0",
  "error": {
    "code": -32001,
    "message": "Unauthorized Tool Call"
  },
  "id": "request-id"
}
```

The original JSON-RPC `id` is preserved and the blocked request is never sent downstream.

## Task 3: Streaming PII guardrail

The gateway accepts a generation request and streams provider output back as SSE while redacting:

- email addresses
- US SSNs
- credit-card-like numbers that pass a Luhn checksum

The key implementation detail is `StreamingPIIRedactor`. It does not buffer the full response. It emits safe completed text immediately and retains only a bounded unresolved suffix that might become PII when the next chunk arrives.

Example upstream chunks:

```text
"Contact jane.do"
"e@example."
"com and SSN 123-"
"45-6789"
```

Client-visible output:

```text
Contact [REDACTED] and SSN [REDACTED]
```

Tests split each supported PII value at every possible two-chunk boundary, plus one-character chunking, to verify that chunk boundaries cannot bypass redaction.

Run the mock provider:

```bash
make mock-llm
```

Run the gateway:

```bash
make task3
```

Example:

```bash
curl -N -X POST http://127.0.0.1:9200/v1/generate \
  -H 'content-type: application/json' \
  -d '{"prompt":"show pii"}'
```

## Task 4: Token limiter and resilient model router

### Rate limiting

Each tenant API key receives a 50,000-token rolling 60-second budget by default.

The limiter uses an on-disk SQLite ledger with:

- `BEGIN IMMEDIATE` for atomic check-and-reserve operations
- WAL mode
- tenant/time index
- SHA-256 tenant identifiers so raw API keys are not stored on disk
- eviction of expired events
- request reservations before the upstream call
- reconciliation from reserved tokens to actual provider usage after success
- reservation release when the model request fails

Reserving capacity before the provider call prevents concurrent requests from independently seeing the same remaining budget and collectively overshooting it.

### Fallback behavior

```text
request
   |
   v
primary model
   |
   +-- success --------------------> return primary response
   |
   +-- HTTP 429 -------------------> secondary model
   |
   +-- timeout after 3000 ms ------> cancel primary, then secondary model
   |
   +-- other provider failure -----> standardized gateway error
```

The code intentionally falls back only for the two conditions named in the assessment: primary 429 and primary timeout. A malformed request or unrelated primary failure is not blindly replayed to another provider.

Run the mock providers:

```bash
make mock-llm
```

Run the router:

```bash
make task4
```

Example:

```bash
curl -X POST http://127.0.0.1:9300/v1/completions \
  -H 'content-type: application/json' \
  -H 'X-API-Key: tenant-demo' \
  -d '{"prompt":"hello","max_tokens":100}'
```

Fallback demos:

```bash
# Primary returns 429, secondary should answer.
curl -X POST http://127.0.0.1:9300/v1/completions \
  -H 'content-type: application/json' \
  -H 'X-API-Key: tenant-demo' \
  -d '{"prompt":"trigger-429","max_tokens":100}'

# Primary exceeds 3 seconds, secondary should answer.
curl -X POST http://127.0.0.1:9300/v1/completions \
  -H 'content-type: application/json' \
  -H 'X-API-Key: tenant-demo' \
  -d '{"prompt":"trigger-timeout","max_tokens":100}'
```

## Error-sanitization policy

External responses never include raw upstream exception text, stack traces, filesystem paths, or provider response bodies. Internal logs keep diagnostics for operators while client responses use stable gateway error codes such as:

- `RATE_LIMIT_EXCEEDED`
- `UPSTREAM_ERROR`
- `UPSTREAM_UNAVAILABLE`
- `GATEWAY_INTERNAL_ERROR`

Each HTTP gateway error response includes a generated `request_id` for correlation.

## Testing strategy

The suite is intentionally aligned to the assessment's evaluation criteria rather than only exercising happy paths.

Notable tests include:

- malformed MCP customer IDs, negative amounts, NaN/infinity, short reasons, extra fields
- real MCP stdio subprocess handshake and `-32602` validation behavior
- viewer `admin_*` call returns `-32001` and produces exactly zero downstream calls
- JSON-RPC request ID preservation
- email, SSN, and card redaction across every possible chunk boundary
- invalid-Luhn long numbers remain untouched
- streaming carry state remains bounded
- concurrent SQLite reservations cannot overshoot a tenant limit
- sliding-window expiry and state eviction
- primary 429 fallback
- primary timeout cancellation before backup execution
- non-429 provider errors do not trigger unintended fallback
- rate-limit reservation reconciliation to actual usage

Run everything:

```bash
pytest
```

## Design tradeoffs

### Why SQLite instead of an in-memory counter?

The assessment requires on-disk SQLite. A ledger also makes sliding-window eviction explicit and testable. A distributed production gateway would typically move this state to a shared low-latency store such as Redis, but that would violate the requested storage choice here.

### Why a token estimate before the provider responds?

Rate limiting must happen before accepting the work. The router reserves estimated prompt tokens plus `max_tokens`, then reconciles to actual usage. This is safer under concurrency than charging only after completion.

### Why Luhn validation for card numbers?

Regex alone produces many false positives for long digit sequences. Luhn is inexpensive and reduces accidental redaction while still operating incrementally.

### Why JWT for the MCP gateway demo?

The requirement asks for a bearer token that yields a role. A signed JWT makes that trust boundary explicit without requiring an external identity provider. Production deployments should validate issuer/audience and use asymmetric signing or an organization identity platform.

## Production extensions

If these components were promoted beyond the assessment, the next changes would be:

- provider-specific tokenizers instead of the portable byte-length estimator
- asymmetric JWT verification with issuer/audience validation and key rotation
- distributed rate-limit storage for horizontally scaled gateway instances
- OpenTelemetry traces and metrics
- secret manager integration
- TLS/mTLS between internal gateway hops
- configurable PII policy by tenant and jurisdiction

Those are intentionally documented rather than added to the take-home implementation so the submitted code stays focused on the requested behavior.
