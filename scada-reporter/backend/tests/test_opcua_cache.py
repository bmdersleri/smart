"""OPC UA server son-değeri cache'ten yayınlar."""

from datetime import UTC, datetime

import pytest

from app.collector.cache import latest_cache
from app.collector.opcua_server import OpcUaServer


class _FakeNode:
    def __init__(self):
        self.written = None

    async def write_value(self, variant):
        self.written = variant


@pytest.mark.asyncio
async def test_opcua_apply_latest_from_cache():
    srv = OpcUaServer()
    node_good = _FakeNode()
    node_null = _FakeNode()
    srv._tag_nodes = {7001: node_good, 7002: node_null}

    latest_cache.update(7001, 12.5, 192, datetime.now(UTC))
    latest_cache.update(7002, None, 0, datetime.now(UTC))

    updated = await srv._apply_latest()

    assert updated == 1
    assert node_good.written is not None  # value written
    assert node_null.written is None  # None value skipped
