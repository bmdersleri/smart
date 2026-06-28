from __future__ import annotations

# ruff: noqa: E402

import sys
from pathlib import Path

import click
import pytest


ROOT = Path(__file__).resolve().parents[3]
AGENT_SRC = ROOT / "scada-reporter" / "agent-harness" / "src"
SKILL_FILE = ROOT / "scada-reporter" / "agent-harness" / "skills" / "SKILL.md"

if str(AGENT_SRC) not in sys.path:
    sys.path.insert(0, str(AGENT_SRC))

from mcp_scada import server as srv
from scada_core.agent_contract import AGENT_RESOURCE_URIS
from scada_core.prompts import PROMPTS
from scada_reporter_cli.cli import cli


def _documented_cli_paths() -> set[str]:
    paths: set[str] = set()
    for raw_line in SKILL_FILE.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line.startswith("- scada "):
            continue
        tokens = line.removeprefix("- scada ").split()
        command_parts: list[str] = []
        for token in tokens:
            if token.startswith(("[", "<", "--", '"', "'")):
                break
            command_parts.append(token)
        if command_parts:
            paths.add(" ".join(command_parts))
    return paths


def _click_leaf_paths(group: click.Group, prefix: tuple[str, ...] = ()) -> set[str]:
    paths: set[str] = set()
    if not isinstance(group, click.Group):
        if prefix:
            paths.add(" ".join(prefix))
        return paths

    for name, command in group.commands.items():
        current = prefix + (name,)
        if isinstance(command, click.Group) and command.commands:
            paths |= _click_leaf_paths(command, current)
            continue
        paths.add(" ".join(current))
    return paths


@pytest.mark.asyncio
async def test_agent_contract_surface_stays_in_sync():
    documented = _documented_cli_paths()
    actual = _click_leaf_paths(cli)

    assert documented == actual, (
        f"CLI contract drift detected.\n"
        f"missing from CLI: {sorted(documented - actual)}\n"
        f"undocumented in SKILL.md: {sorted(actual - documented)}"
    )

    prompts = await srv.mcp.list_prompts()
    prompt_names = {prompt.name for prompt in prompts}
    assert prompt_names == set(PROMPTS), (
        f"Prompt contract drift detected.\n"
        f"missing from MCP: {sorted(set(PROMPTS) - prompt_names)}\n"
        f"extra in MCP: {sorted(prompt_names - set(PROMPTS))}"
    )

    resources = await srv.mcp.list_resources()
    resource_uris = {str(resource.uri) for resource in resources}
    expected_resources = {"scada://tags", "scada://plcs", "scada://schema"} | set(
        AGENT_RESOURCE_URIS
    )
    assert resource_uris == expected_resources, (
        f"Resource contract drift detected.\n"
        f"missing from MCP: {sorted(expected_resources - resource_uris)}\n"
        f"extra in MCP: {sorted(resource_uris - expected_resources)}"
    )
