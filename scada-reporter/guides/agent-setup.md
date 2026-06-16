# Agent Setup — SCADA Reporter

## 1. Start the Backend

```bash
cd scada-reporter
just run-backend
# → http://localhost:8001
```

## 2. Install the Agent CLI

```bash
uv pip install -e scada-reporter/agent-harness
```

Verify:

```bash
scada --help
scada health
```

## 3. Log In

```bash
scada auth login admin
```

## 4. Configure Your Agent

### Claude Code

```bash
# Install the plugin
/plugin marketplace add <project-repo>

# Plugin commands:
/scada-login
/scada-tags list
/scada-dashboard current-values
```

### OpenCode

The `AGENTS.md` file is loaded automatically. You can use the agent CLI commands directly.

### Other Agents (Cursor, Copilot, Windsurf)

```bash
# In your agent prompts:
scada <command> --json
```

JSON output is easily processed by any agent.
