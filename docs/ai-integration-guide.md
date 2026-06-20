# Ekont Smart Scada Reporter — AI Integration Roadmap

A practical guide to maturing the AI/agent capabilities of the platform from its current foundation to a state-of-the-art agent-native reporting system.

---

## Current State

The project already has a strong agent-native foundation:

| Layer | Status |
|-------|--------|
| **Agent CLI** (`scada`) | Working — 8 command groups (agent grubu eklendi), JSON output, REPL mode |
| **MCP Protocol** | Working — 2 MCP servers (scada + db), 15 tools |
| **Backend AI Endpoints** | Working — NL query, anomaly detection, trend prediction, auto-report, health |
| **Agent Definitions** | 3 OpenCode agents (scada-operator, scada-analyst, scada-reporter), 4 slash commands |
| **AI Skills** | 7 caveman skills installed |
| **CodeGraph** | Running daemon for code intelligence |
| **Memory System** | Created — .memory/decisions.yaml, knowledge.md, session scratchpad |
| **Agent Workflows** | CLI-based — monitor, ask, anomalies, forecast, status commands |

---

## Phase 1: MCP Server Layer (Foundation)

### 1.1 Create a SCADA MCP Server

Build a dedicated Python MCP server (`mcp-server-scada`) that wraps the existing `scada` CLI commands as MCP tools. This lets any MCP-compatible agent (Claude, ChatGPT, Gemini, OpenCode) connect directly.

```python
# mcp-server-scada/src/mcp_server_scada/server.py
from mcp.server import Server
from mcp.types import Tool, TextContent
import httpx
import os

SCADA_API_URL = os.getenv("SCADA_API_URL", "http://localhost:8001")

server = Server("ekont-scada")

@server.list_tools()
async def list_tools():
    return [
        Tool(
            name="query_current_values",
            description="Get current values for specified tags or all active tags",
            inputSchema={
                "type": "object",
                "properties": {
                    "tags": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Tag names to query (optional, returns all if empty)"
                    }
                }
            }
        ),
        Tool(
            name="query_trend",
            description="Query historical trend data for one or more tags",
            inputSchema={
                "type": "object",
                "properties": {
                    "tags": {"type": "array", "items": {"type": "string"}},
                    "start": {"type": "string", "description": "ISO 8601 start time"},
                    "end": {"type": "string", "description": "ISO 8601 end time"},
                    "bucket": {"type": "string", "description": "Aggregation bucket (e.g. 1h, 1d)"}
                },
                "required": ["tags", "start", "end"]
            }
        ),
        Tool(
            name="generate_report",
            description="Generate a report for given tags and time range",
            inputSchema={
                "type": "object",
                "properties": {
                    "tags": {"type": "array", "items": {"type": "string"}},
                    "start": {"type": "string"}, "end": {"type": "string"},
                    "format": {"type": "string", "enum": ["excel", "pdf", "json", "csv"]},
                    "aggregation": {"type": "string", "enum": ["hourly", "daily", "monthly"]}
                },
                "required": ["tags", "start", "end"]
            }
        ),
        Tool(
            name="list_tags",
            description="List all tags with their current status and metadata",
            inputSchema={"type": "object", "properties": {
                "active_only": {"type": "boolean"},
                "search": {"type": "string"}
            }}
        ),
        Tool(
            name="list_plcs",
            description="List all configured PLCs and their connection status",
            inputSchema={"type": "object", "properties": {}}
        ),
        Tool(
            name="check_health",
            description="Check system health status",
            inputSchema={"type": "object", "properties": {}}
        ),
        Tool(
            name="run_sql_query",
            description="Execute a read-only SQL query on the timeseries database",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "SELECT / WITH / EXPLAIN query only"}
                },
                "required": ["query"]
            }
        ),
    ]

@server.call_tool()
async def call_tool(name: str, arguments: dict):
    async with httpx.AsyncClient() as client:
        # Map MCP tool calls to scada CLI / REST API endpoints
        ...
```

**Deployment options:**
- Run as a subprocess alongside the backend (stdio transport)
- Run as a standalone HTTP server (SSE transport) on a dedicated port
- Package as a PyPI-installable plugin (`pip install mcp-server-scada`)

### 1.2 Create a Database MCP Server

Expose the PostgreSQL/TimescaleDB schema as MCP tools so agents can discover table structures, column types, and relationships autonomously.

```python
@server.list_tools()
async def list_tools():
    return [
        Tool(name="list_tables", description="List all tables and views in the database", ...),
        Tool(name="describe_table", description="Get column names, types, and constraints for a table", ...),
        Tool(name="get_tag_schema", description="Get the tags catalog schema with unit ranges", ...),
    ]
```

### 1.3 Create an MCP Configuration File

Add an `mcp.json` at the project root so MCP-compatible agents discover the servers automatically:

```json
{
  "mcpServers": {
    "scada": {
      "command": "uv",
      "args": ["run", "mcp-server-scada"],
      "env": {
        "SCADA_API_URL": "http://localhost:8001"
      }
    },
    "filesystem": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-filesystem", "C:\\project\\smart"]
    }
  }
}
```

> **Note:** The former `scada-db` MCP server (direct-DB SQL) has been removed. Read-only SQL queries are now served by the API's `run_sql_query` tool via the `scada` MCP server.

---

## Phase 2: Backend AI Endpoints

### 2.1 Natural Language Query Endpoint

Add a `/api/ai/query` endpoint that accepts natural language questions and returns structured answers:

```
POST /api/ai/query
{
  "question": "What was the average pH value in the last 24 hours?",
  "llm_provider": "openai" | "claude" | "local"
}
```

**Architecture:**
1. User/agent submits a natural language question
2. LLM translates the question to a structured query plan (tag selection + aggregation + time range)
3. Execute against the timeseries database
4. LLM formulates the natural language response with optional chart data

```python
@router.post("/ai/query")
async def ai_query(request: AIQueryRequest):
    # Step 1: Extract intent using LLM
    query_plan = await llm_router.extract_query_plan(request.question)

    # Step 2: Resolve tag names (handle synonyms, fuzzy matching)
    tags = await tag_resolver.resolve(query_plan.tag_descriptions)

    # Step 3: Execute the data query
    data = await timeseries.query(
        tags=tags,
        aggregation=query_plan.aggregation,
        time_range=query_plan.time_range
    )

    # Step 4: Generate response
    answer = await llm_router.format_answer(data, query_plan)
    return {"answer": answer, "data": data, "chart_config": query_plan.chart_config}
```

### 2.2 Anomaly Detection Service

Build a service that analyzes timeseries data for anomalies and exposes both REST and MCP interfaces:

```python
class AnomalyDetector:
    async def detect(self, tag_id: int, window: str = "7d") -> list[Anomaly]:
        """
        Statistical anomaly detection using:
        - Z-score based thresholding
        - Moving average deviation
        - Seasonal decomposition (STL)
        - Optional: ML model (Isolation Forest) for multivariate
        """
        values = await self.fetch_values(tag_id, window)
        anomalies = []

        # Z-score method
        mean, std = np.mean(values), np.std(values)
        for ts, val in values:
            if abs(val - mean) > 3 * std:
                anomalies.append(Anomaly(timestamp=ts, value=val, z_score=(val-mean)/std))

        return anomalies
```

**API Endpoints:**
- `GET /api/ai/anomalies?tag=...&window=7d` — List detected anomalies
- `GET /api/ai/anomalies/summary` — Summary across all active tags
- `POST /api/ai/alarms` — Configure alarm rules with AI-suggested thresholds

### 2.3 Predictive Trend Service

Add trend prediction using lightweight time-series forecasting:

```python
@router.post("/api/ai/predict")
async def predict_trend(tag: str, horizon: str = "24h"):
    """
    Forecast future values using:
    - Prophet (Meta) for seasonal data
    - ARIMA for stationary trends
    - Linear regression for short-term projection
    """
    history = await timeseries.fetch(tag, window="30d")
    model = await model_registry.get_model(tag)
    forecast = model.predict(history, horizon)
    return {"tag": tag, "forecast": forecast, "confidence_interval": ...}
```

### 2.4 Auto-Report Generation

```python
@router.post("/api/ai/reports/generate")
async def ai_generate_report(prompt: str):
    """
    Accept a natural language report request:
    "Generate a daily water quality report for last week,
     include pH, turbidity, and chlorine, with a summary paragraph"
    """
    report_spec = await llm_router.parse_report_request(prompt)
    data = await gather_report_data(report_spec.tags, report_spec.time_range)
    summary = await llm_router.summarize(data, report_spec)
    excel = await report_engine.generate(data, report_spec, summary)
    return {"excel": excel, "summary": summary}
```

---

## Phase 3: Agent Infrastructure Maturation

### 3.1 Create OpenCode Agent Definitions

Port the most valuable Claude Code agents to OpenCode-compatible format:

```json
// .opencode/agents/auditor.json
{
  "name": "auditor",
  "description": "Self-improving quality gate — reviews code, enforces standards, promotes learnings to knowledge base",
  "model": "big-pickle",
  "tools": ["read", "glob", "grep", "edit", "bash", "todowrite"],
  "instructions": "Review every file change for regressions, style violations, and security issues. Maintain the knowledge base."
}
```

### 3.2 Add OpenCode Slash Commands

```json
// .opencode/commands/scada-query.json
{
  "name": "scada-query",
  "description": "Query SCADA data using natural language",
  "prompt": "Ask a question about your SCADA data, e.g. 'What was the max flow rate yesterday?'"
}
```

### 3.3 Build a Unified Agent Memory System

Replace the scattered `.claude/memory.md` approach with a shared memory system accessible across agents:

- **Short-term memory**: Session context (current task, file changes)
- **Long-term memory**: Knowledge base (architecture decisions, patterns, conventions)
- **Ephemeral memory**: Per-agent scratchpads

Store in a structured format like YAML or JSON for machine readability:

```yaml
# .memory/decisions.yaml
- id: 001
  date: 2026-06-17
  title: MCP Server Protocol Selection
  decision: Use stdio transport for local agents, SSE for remote
  rationale: stdio has lower latency; SSE enables cloud-hosted agents
  status: active
```

### 3.4 Integrate CodeGraph MCP Tools

CodeGraph is already running. Create MCP tools that leverage it:

```
Tool: codegraph_explore — Query code relationships
Tool: codegraph_node — Read file with line numbers
Tool: codegraph_callers — Find callers of a function
```

---

## Phase 4: Smart Agent Workflows

### 4.1 Autonomous Monitoring Agent

An AI agent that runs periodically and:

1. Queries current PLC connection status
2. Checks for stale tags (no update > 5 min)
3. Detects anomalous readings across all active tags
4. Generates a brief status report
5. Pushes alerts via MCP if thresholds are breached

**Trigger:** `scada agent monitor --interval 15m`

### 4.2 Natural Language Dashboard Agent

An agent that translates natural language to dashboard configurations:

> "Show me a trend chart of pump discharge pressure and flow rate for the last 7 days, with daily aggregation"

The agent:
1. Resolves tag names (pump discharge pressure → `PT-101`, flow rate → `FT-101`)
2. Queries the trend data
3. Returns a structured chart configuration
4. The frontend renders it instantly

### 4.3 Report Scheduler Agent

An agent that manages report schedules through conversation:

> "Schedule a daily water quality report at 8 AM, email it to the operations team"

The agent creates the schedule, generates the first report, and confirms.

### 4.4 Predictive Maintenance Agent

An agent that monitors equipment runtime and wear indicators:

1. Tracks cumulative runtime per pump/motor
2. Compares against manufacturer MTBF curves
3. Predicts remaining useful life
4. Schedules maintenance windows
5. Reports via MCP tools

---

## Phase 5: LLM Provider Integration

### 5.1 Multi-Provider Router

Build an abstraction layer that supports multiple LLM providers:

```python
class LLMRouter:
    providers = {
        "claude": ClaudeProvider(api_key=...),
        "openai": OpenAIProvider(api_key=...),
        "gemini": GeminiProvider(api_key=...),
        "local": OllamaProvider(model="llama3", base_url="http://localhost:11434"),
        "azure": AzureOpenAIProvider(...)
    }

    async def route(self, request, preferred_provider=None):
        provider = preferred_provider or self.select_best(request)
        return await provider.complete(request)
```

### 5.2 Context-Aware Prompt Engineering

Build domain-specific prompts for SCADA operations:

- **Query prompts**: Instruct the LLM to always return structured query plans with validated tag names
- **Report prompts**: Define the expected report structure, sections, and tone
- **Alert prompts**: Focus on brevity and actionable information

### 5.3 Local LLM Support for Air-Gapped Deployments

Many industrial sites are air-gapped. Support local models:

```bash
# Deploy with Ollama
ollama pull llama3.1:8b
ollama pull mistral:7b

# Configure
SCADA_LLM_PROVIDER=local
SCADA_LLM_MODEL=llama3.1:8b
SCADA_LLM_ENDPOINT=http://localhost:11434
```

---

## Implementation Priority Matrix

| Feature | Effort | Impact | Phase |
|---------|--------|--------|-------|
| MCP SCADA Server | Medium | High | P1 |
| NL Query Endpoint | High | High | P1 |
| MCP Config File | Low | High | P1 |
| Anomaly Detection | Medium | Medium | P2 |
| Auto-Report Generation | High | High | P2 |
| Predictive Trends | High | Medium | P2 |
| Agent Definitions (OpenCode) | Low | Medium | P2 |
| Local LLM Support | Medium | Medium | P3 |
| Monitoring Agent | Medium | Low | P3 |
| Predictive Maintenance | High | Low | P3 |

---

## Technology Stack Recommendations

| Component | Recommended | Alternative |
|-----------|-------------|-------------|
| **MCP SDK** | `mcp` (Python) | `@modelcontextprotocol/sdk` (TypeScript) |
| **LLM Router** | `litellm` (Python) | Custom implementation |
| **Embeddings** | `sentence-transformers` | `text-embeddings-inference` |
| **Vector Store** | pgvector (PostgreSQL extension) | Qdrant, Chroma |
| **Time-Series ML** | `statsmodels`, `prophet` | `darts`, `pmdarima` |
| **Local LLM** | Ollama + llama3.1 | vLLM, llama.cpp |
| **Agent Framework** | Custom (MCP + FastAPI) | LangChain, CrewAI |

---

## Quick Wins (First Week)

1. **Create `mcp.json`** — 30 minutes, unlocks MCP compatibility
2. **Add `/api/ai/health` endpoint** — 1 hour, agent can verify AI subsystem status
3. **Add tag name fuzzy resolution** — 2 hours, agents can use descriptive tag names
4. **Publish MCP server as PyPI package** — 2 hours, `pip install mcp-server-scada`
5. **Write agent onboarding guide** — 1 hour, reduce setup time for new agents

---

## Measuring Success

| Metric | Current | Target |
|--------|---------|--------|
| MCP tools available | 0 | 12+ |
| AI API endpoints | 0 | 6+ |
| Agent workflows automated | 0 | 4+ |
| Backend response to NL queries | N/A | < 5s |
| Anomaly detection latency | N/A | < 1s per tag |

---

## References

- [Model Context Protocol Specification](https://modelcontextprotocol.io)
- [MCP Python SDK](https://github.com/modelcontextprotocol/python-sdk)
- [OpenCode Documentation](https://opencode.ai)
- [TimescaleDB + pgvector](https://docs.timescale.com/use-timescale/latest/vector)
- [Ollama](https://ollama.ai) for local LLM deployments

---

*Ekont Smart Scada Reporter — AI integration roadmap for an agent-native reporting system.*
