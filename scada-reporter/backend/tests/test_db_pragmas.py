import sqlite3

from app.core.database import set_sqlite_pragmas


def test_sqlite_pragmas_applied(tmp_path):
    con = sqlite3.connect(str(tmp_path / "t.db"))
    set_sqlite_pragmas(con)
    assert con.execute("PRAGMA journal_mode").fetchone()[0].lower() == "wal"
    assert con.execute("PRAGMA synchronous").fetchone()[0] == 1  # NORMAL
    assert con.execute("PRAGMA busy_timeout").fetchone()[0] == 30000
    assert con.execute("PRAGMA cache_size").fetchone()[0] == -64000  # 64 MB
    assert con.execute("PRAGMA mmap_size").fetchone()[0] == 268435456  # 256 MB
    assert con.execute("PRAGMA wal_autocheckpoint").fetchone()[0] == 1000
    con.close()
