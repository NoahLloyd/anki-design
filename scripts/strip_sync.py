#!/usr/bin/env python3
"""Remove AnkiWeb sync credentials from a (copied) Anki prefs21.db.

`make seed` rsyncs your real base into the worktree's dev base. That copy
includes prefs21.db, which holds your AnkiWeb login (`syncKey`/`syncUser`)
and `autoSync`. Without this step a seeded dev instance would log into your
real AnkiWeb account and auto-sync — pulling your real data and pushing test
changes back. Clearing the auth keys makes Anki treat the dev profile as
logged out, so it is a fully local, inert snapshot that cannot touch your
account. (Anki reads profiles with pickle; it writes protocol=4, so we match.)

Usage:  strip_sync.py /path/to/prefs21.db
"""

import pickle
import sqlite3
import sys

# syncKey/syncUser absent => Anki is "logged out" and cannot sync at all.
# The rest are cleared for cleanliness; autoSync=False is belt-and-suspenders.
SYNC_KEYS = (
    "syncKey",
    "syncUser",
    "hostNum",
    "currentSyncUrl",
    "customSyncUrl",
)


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: strip_sync.py /path/to/prefs21.db", file=sys.stderr)
        return 2
    db = sys.argv[1]
    con = sqlite3.connect(db)
    try:
        rows = con.execute("select name, data from profiles").fetchall()
        changed = 0
        for name, data in rows:
            if name == "_global" or data is None:
                continue
            try:
                prof = pickle.loads(data)
            except Exception:
                continue
            if not isinstance(prof, dict):
                continue
            before = dict(prof)
            for k in SYNC_KEYS:
                prof.pop(k, None)
            prof["autoSync"] = False
            if prof != before:
                con.execute(
                    "update profiles set data = ? where name = ?",
                    (pickle.dumps(prof, protocol=4), name),
                )
                changed += 1
        con.commit()
    finally:
        con.close()
    print(f"strip_sync: cleared AnkiWeb sync from {changed} profile(s) in {db}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
