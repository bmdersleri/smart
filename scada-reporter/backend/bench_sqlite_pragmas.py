"""Measure #3: SQLite pragma tuning (cache_size/mmap_size) on a read workload.

Bulk-load N rows into a file-backed SQLite DB, then run M range-scan
aggregations. Compare default pragmas vs the tuned set added in database.py.
Fresh process/connection per variant so the page cache starts cold.
"""

import sqlite3
import sys
import time

N = 300_000
M = 60  # range-scan queries
DBFILE = sys.argv[1] if len(sys.argv) > 1 else "bench_pragma.db"


def build(path):
    con = sqlite3.connect(path)
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("CREATE TABLE r (tag_id int, value real, ts int, PRIMARY KEY(tag_id, ts))")
    rows = ((tid, float(tid), t) for t in range(N // 50) for tid in range(1, 51))
    con.executemany("INSERT INTO r (tag_id, value, ts) VALUES (?,?,?)", rows)
    con.commit()
    con.close()


def run(path, *, tuned):
    con = sqlite3.connect(path)
    cur = con.cursor()
    cur.execute("PRAGMA journal_mode=WAL")
    cur.execute("PRAGMA synchronous=NORMAL")
    if tuned:
        cur.execute("PRAGMA cache_size=-64000")
        cur.execute("PRAGMA mmap_size=268435456")
        cur.execute("PRAGMA wal_autocheckpoint=1000")
    t0 = time.perf_counter()
    span = (N // 50) // M
    for i in range(M):
        lo, hi = i * span, (i + 4) * span  # overlapping windows → repeated page reads
        cur.execute("SELECT count(*), avg(value) FROM r WHERE ts BETWEEN ? AND ?", (lo, hi))
        cur.fetchall()
    dt = time.perf_counter() - t0
    con.close()
    return dt


def main():
    import os

    for suffix in ("", "-wal", "-shm"):
        p = DBFILE + suffix
        if os.path.exists(p):
            os.remove(p)
    build(DBFILE)
    # run each variant twice, take the min (reduce noise)
    default = min(run(DBFILE, tuned=False) for _ in range(3))
    tuned = min(run(DBFILE, tuned=True) for _ in range(3))
    print(f"rows={N:,}  queries={M}")
    print(f"default pragmas : {default:6.3f}s")
    print(f"tuned   pragmas : {tuned:6.3f}s")
    print(f"#3 speedup      : {default / tuned:5.2f}x  ({(1 - tuned / default) * 100:.1f}% faster)")
    for suffix in ("", "-wal", "-shm"):
        p = DBFILE + suffix
        if os.path.exists(p):
            os.remove(p)


main()
