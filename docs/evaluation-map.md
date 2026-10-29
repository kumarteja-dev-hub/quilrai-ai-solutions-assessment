# Assessment evaluation map

This file maps each requested scoring area to the implementation and the test that demonstrates it.

| Assessment area | Implementation | Verification |
|---|---|---|
| Task 1 strict validation | `task1_mcp_server/models.py` | `test_task1_models.py` |
| Task 1 standard JSON-RPC errors | `task1_mcp_server/server.py` raises `MCPError(-32602)` | `test_task1_mcp_wire.py` |
| Task 1 stdio isolation | official `stdio_server()` plus stderr logging | real subprocess MCP client integration test |
| Task 1 protocol compliance | official MCP SDK low-level `Server` | MCP client list/call integration test |
| Task 2 JSON-RPC parsing | `JSONRPCRequest` | gateway tests |
| Task 2 forwarding | `SecurityGateway.handle()` | `test_tools_list_is_forwarded_transparently` |
| Task 2 fine-grained auth | signed JWT role + `admin_*` policy | viewer/admin gateway tests |
| Task 2 blocked call never forwarded | policy executes before `client.post()` | downstream call counter asserts zero |
| Task 3 async streaming | provider async iterator + `StreamingResponse` | `test_task3_app.py` |
| Task 3 partial-stream matching | `StreamingPIIRedactor` unresolved suffix state | every split-position test |
| Task 3 memory efficiency | bounded carry only | 10,000-character pathological-token test |
| Task 4 token sliding window | `SQLiteSlidingWindowRateLimiter` | expiry/eviction test |
| Task 4 concurrency | `BEGIN IMMEDIATE` atomic reservation | 20 concurrent reservation test |
| Task 4 429 fallback | `ResilientModelRouter._call_with_fallback()` | router 429 test |
| Task 4 3000 ms timeout fallback | `asyncio.wait_for` | timeout cancellation test |
| Task 4 sanitized errors | `GatewayError` public contract | provider failure test |
| Task 4 on-disk SQLite | configured database path | rate limiter implementation/tests |
