"""Block-read planner ve blok-okuma testleri."""

import struct

from app.collector.s7_collector import DbBlock, PLCConnection, ReadSpec, plan_db_blocks


def test_plan_db_blocks_coalesces_adjacent():
    items = [
        (0, ReadSpec("DB", 10, 0, 0, 4, "REAL")),
        (1, ReadSpec("DB", 10, 4, 0, 2, "WORD")),
        (2, ReadSpec("DB", 10, 8, 0, 4, "REAL")),
    ]
    blocks = plan_db_blocks(items)
    assert len(blocks) == 1
    b = blocks[0]
    assert isinstance(b, DbBlock)
    assert (b.db_number, b.start, b.size) == (10, 0, 12)
    assert [key for key, _ in b.members] == [0, 1, 2]


def test_plan_db_blocks_splits_on_large_gap():
    items = [
        (0, ReadSpec("DB", 10, 0, 0, 4, "REAL")),
        (1, ReadSpec("DB", 10, 5000, 0, 4, "REAL")),
    ]
    blocks = plan_db_blocks(items)
    assert len(blocks) == 2
    assert all(b.size == 4 for b in blocks)


def test_plan_db_blocks_separates_by_db_number():
    items = [
        (0, ReadSpec("DB", 10, 0, 0, 4, "REAL")),
        (1, ReadSpec("DB", 20, 0, 0, 4, "REAL")),
    ]
    blocks = plan_db_blocks(items)
    assert {b.db_number for b in blocks} == {10, 20}


def test_plan_db_blocks_caps_block_span():
    # specs 30 bytes apart (gap 26 <= tolerance) chained past MAX_BLOCK_BYTES (222)
    items = [(i, ReadSpec("DB", 10, i * 30, 0, 4, "REAL")) for i in range(10)]
    blocks = plan_db_blocks(items)
    assert len(blocks) >= 2
    assert all(b.size <= 222 for b in blocks)


def test_plan_db_blocks_empty():
    assert plan_db_blocks([]) == []


class _FakeClient:
    def __init__(self, db_data: dict[int, bytes]):
        self._db = db_data
        self.db_read_calls = 0

    def db_read(self, db: int, start: int, size: int) -> bytearray:
        self.db_read_calls += 1
        return bytearray(self._db[db][start : start + size])

    def read_area(self, area, dbnum, start, size):  # noqa: ANN001
        return bytearray(b"\x00" * size)

    def get_connected(self) -> bool:
        return True


def test_read_batch_sync_uses_single_block_read():
    buf = bytearray(16)
    struct.pack_into(">f", buf, 0, 3.5)  # REAL @0
    struct.pack_into(">H", buf, 4, 7)  # WORD @4
    conn = PLCConnection("10.0.0.9")
    conn._client = _FakeClient({10: bytes(buf)})
    conn._connected = True

    specs = [
        ReadSpec("DB", 10, 0, 0, 4, "REAL"),
        ReadSpec("DB", 10, 4, 0, 2, "WORD"),
    ]
    results = conn.read_batch_sync(specs)

    assert results == [(3.5, 192), (7.0, 192)]
    assert conn._client.db_read_calls == 1  # both tags in one round-trip


def test_read_batch_sync_preserves_input_order():
    buf = bytearray(16)
    struct.pack_into(">f", buf, 8, 1.25)
    struct.pack_into(">f", buf, 0, 9.0)
    conn = PLCConnection("10.0.0.9")
    conn._client = _FakeClient({10: bytes(buf)})
    conn._connected = True

    specs = [
        ReadSpec("DB", 10, 8, 0, 4, "REAL"),  # higher offset first
        ReadSpec("DB", 10, 0, 0, 4, "REAL"),
    ]
    results = conn.read_batch_sync(specs)
    assert results == [(1.25, 192), (9.0, 192)]
