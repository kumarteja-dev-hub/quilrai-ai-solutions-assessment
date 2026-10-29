# Architecture

## Task 1: MCP stdio server

```mermaid
flowchart LR
    C[MCP Client] -->|stdin JSON-RPC| S[Official MCP SDK Server]
    S --> V[Pydantic strict validation]
    V --> T1[get_customer_record]
    V --> T2[trigger_refund]
    S -->|stdout JSON-RPC only| C
    S -->|diagnostics| E[stderr]
```

The low-level official SDK API is used because this task explicitly requests standard JSON-RPC errors for invalid parameters. Pydantic models generate the advertised JSON Schema and validate runtime arguments. Validation failures are converted to `MCPError` with `-32602`.

## Task 2: MCP security gateway

```mermaid
flowchart LR
    A[AI Agent] -->|Bearer JWT + JSON-RPC| G[Security Gateway]
    G --> J[JWT verification]
    J --> P[Method and tool policy]
    P -->|allowed| D[Downstream MCP server]
    P -->|viewer + admin_*| X[-32001 Unauthorized Tool Call]
```

Authorization is enforced before a downstream request object is created. Tests count downstream calls to prove blocked actions do not escape the gateway.

## Task 3: Streaming PII guardrail

```mermaid
flowchart LR
    C[Client] --> G[Streaming Gateway]
    G --> P[LLM Provider]
    P -->|small text deltas| R[Stateful PII Redactor]
    R -->|safe deltas| C
    R -->|unresolved suffix only| B[Bounded carry state]
```

The redactor delays only text that could still become a supported sensitive pattern when a future chunk arrives. It does not collect the entire model response.

## Task 4: Resilient model router

```mermaid
flowchart TD
    C[Completion Request] --> L[SQLite Sliding Window Limiter]
    L -->|reserve capacity| P[Primary Provider]
    P -->|success| R[Reconcile actual token usage]
    P -->|429| S[Secondary Provider]
    P -->|3 second timeout| K[Cancel primary]
    K --> S
    S -->|success| R
    P -->|other failure| E[Sanitized Gateway Error]
    S -->|failure| E
    R --> C
```

The limiter's check and reservation occur in a single SQLite `BEGIN IMMEDIATE` transaction, which prevents concurrent callers from spending the same remaining budget.
