"""Write posts, engagement snapshots and run records."""
import json
from datetime import datetime, timedelta

import pandas as pd

POST_COLS = ["source", "source_id", "url", "kind", "community", "author", "parent_id", "title", "text",
             "media_type", "published_at", "score", "likes", "views", "comments", "raw"]
METRICS = ["score", "likes", "views", "comments"]


def save(con, items):
    """Upsert posts and add one engagement snapshot per item. Returns (new, updated)."""
    if not items:
        return 0, 0
    now = datetime.now()
    df = pd.DataFrame([{c: i.get(c) for c in POST_COLS} for i in items])
    df = df.drop_duplicates(subset=["source", "source_id"], keep="last")
    df["raw"] = df["raw"].map(lambda r: json.dumps(r, default=str) if r is not None else None)
    for m in METRICS:
        df[m] = pd.array(df[m], dtype="Int64")
    df["first_seen_at"] = now
    df["last_seen_at"] = now

    con.register("_new", df)
    existing = con.execute("""SELECT count(*) FROM _new n JOIN posts p
                              ON p.source = n.source AND p.source_id = n.source_id""").fetchone()[0]
    con.execute("""
        INSERT INTO posts (source, source_id, url, kind, community, author, parent_id, title, text, media_type,
                           published_at, first_seen_at, last_seen_at, score, likes, views, comments, raw)
        SELECT source, source_id, url, kind, community, author, parent_id, title, text, media_type,
               published_at, first_seen_at, last_seen_at, score, likes, views, comments, raw FROM _new
        ON CONFLICT (source, source_id) DO UPDATE SET
            title = excluded.title, text = excluded.text, last_seen_at = excluded.last_seen_at,
            score = coalesce(excluded.score, posts.score), likes = coalesce(excluded.likes, posts.likes),
            views = coalesce(excluded.views, posts.views), comments = coalesce(excluded.comments, posts.comments),
            raw = excluded.raw
    """)
    con.execute("""INSERT OR IGNORE INTO post_snapshots
                   SELECT source, source_id, ?, score, likes, views, comments FROM _new""", [now])
    con.unregister("_new")
    return len(df) - existing, existing


def recent_ids(con, source, window_days, kind=None):
    """Ids of posts published within the snapshot window, for re-measuring engagement."""
    since = datetime.now() - timedelta(days=window_days)
    q = "SELECT source_id FROM posts WHERE source = ? AND published_at >= ?"
    params = [source, since]
    if kind:
        q += " AND kind = ?"
        params.append(kind)
    return [r[0] for r in con.execute(q, params).fetchall()]


def log_run(con, source, started, new, updated, snaps, errors, status, note=""):
    con.execute("INSERT INTO collector_runs VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                [source, started, datetime.now(), new, updated, snaps, errors, status, note[:2000]])
