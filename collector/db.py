"""Local DuckDB storage for collected posts. The database file never leaves the machine."""
import os

import duckdb
from dotenv import load_dotenv

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(ROOT, "data", "reddit.duckdb")
load_dotenv(os.path.join(ROOT, ".env"))

SCHEMA = """
CREATE TABLE IF NOT EXISTS posts (
    source        VARCHAR NOT NULL,
    source_id     VARCHAR NOT NULL,   -- Reddit fullname (t3_ post, t1_ comment)
    url           VARCHAR,
    kind          VARCHAR,            -- post | comment
    community     VARCHAR,            -- subreddit
    author        VARCHAR,            -- salted one-way hash, never the username
    parent_id     VARCHAR,
    title         VARCHAR,
    text          VARCHAR,
    media_type    VARCHAR,
    published_at  TIMESTAMP,
    first_seen_at TIMESTAMP,
    last_seen_at  TIMESTAMP,
    score         BIGINT,
    likes         BIGINT,
    views         BIGINT,
    comments      BIGINT,
    raw           JSON,
    PRIMARY KEY (source, source_id)
);
CREATE TABLE IF NOT EXISTS post_snapshots (
    source VARCHAR NOT NULL, source_id VARCHAR NOT NULL, captured_at TIMESTAMP NOT NULL,
    score BIGINT, likes BIGINT, views BIGINT, comments BIGINT,
    PRIMARY KEY (source, source_id, captured_at)
);
CREATE TABLE IF NOT EXISTS collector_runs (
    source VARCHAR, started_at TIMESTAMP, finished_at TIMESTAMP, new_items INTEGER, updated INTEGER,
    snapshots INTEGER, errors INTEGER, status VARCHAR, note VARCHAR
);
"""


def connect():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    con = duckdb.connect(DB_PATH)
    con.execute(SCHEMA)
    return con
