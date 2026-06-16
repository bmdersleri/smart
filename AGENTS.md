# SCADA Reporter — Agent Usage Guide

This project is structured **agent-native** following the CLI-Anything approach.
Detailed guide: `scada-reporter/AGENTS.md`

## Quick Links

| Need | Location |
|------|----------|
| Agent CLI source | `scada-reporter/agent-harness/` |
| Claude Code plugin | `scada-reporter/.claude-plugin/` |
| Slash commands | `scada-reporter/commands/` |
| Guides | `scada-reporter/guides/` |
| SKILL.md | `scada-reporter/agent-harness/skills/SKILL.md` |

## Setup (30 seconds)

```bash
cd scada-reporter
uv pip install -e agent-harness
scada auth login admin --password <password>
scada tags list
```
