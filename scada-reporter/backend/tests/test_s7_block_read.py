"""Block-read planner ve blok-okuma testleri."""

from app.collector.s7_collector import DbBlock, ReadSpec, plan_db_blocks


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
