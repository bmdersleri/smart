# Knowledge Base

## Architecture

- Ekont Smart Scada Reporter: web-based AI agent-powered reporting system
- Backend: Python 3.14, FastAPI, SQLAlchemy async, TimescaleDB, asyncpg
- Frontend: Vue 3 + Vite + TypeScript
- Agent CLI: Python Click framework, httpx client
- MCP Servers: Python mcp package, stdio transport

## Naming Conventions

- Product name: Ekont Smart Scada Reporter (not "SCADA Reporter")
- Components: Ekont Universal Collector (Snap7), Ekont Smart Recording System (deadband), Ekont OPC UA Server (OPC UA Server)
- Tag naming: descriptive names (e.g., PT-101, FT-101, pH-001)

## API Patterns

- All AI endpoints under /api/ai/
- Authentication via JWT Bearer token (get_current_user dependency)
- All responses include descriptive error messages
- Pagination with offset/limit pattern

## Agent Conventions

- Primary model: big-pickle
- Tools: read, glob, grep, bash, question, todowrite (+ websearch for analyst)
- MCP servers: scada (read-only SQL via run_sql_query tool; mcp-db removed)
- Agent configs in .opencode/agents/*.json
- Slash commands in .opencode/commands/*.json
