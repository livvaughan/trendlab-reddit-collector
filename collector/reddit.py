"""Reddit collector: posts (new + today's top) and comments on high-scoring posts, via the official API.

App-only OAuth (client id + secret, no Reddit password). Free tier: 100 requests/minute, non-commercial use.
Each run also re-measures score and comment count on posts from the last `snapshots.window_days`.
"""
import hashlib
import logging
import os
import time
from datetime import datetime

import requests

from collector import store
from collector.http import ApiError, request

log = logging.getLogger("trendlab.social")
API = "https://oauth.reddit.com"


class Reddit:
    def __init__(self):
        self.id = os.environ.get("REDDIT_CLIENT_ID")
        self.secret = os.environ.get("REDDIT_CLIENT_SECRET")
        self.ua = os.environ.get("REDDIT_USER_AGENT")
        self.salt = os.environ.get("AUTHOR_HASH_SALT")
        missing = [k for k, v in {"REDDIT_CLIENT_ID": self.id, "REDDIT_CLIENT_SECRET": self.secret,
                                  "REDDIT_USER_AGENT": self.ua, "AUTHOR_HASH_SALT": self.salt}.items() if not v]
        if missing:
            raise ApiError(f"missing in .env: {', '.join(missing)}")
        self.s = requests.Session()
        self.s.headers["User-Agent"] = self.ua
        self.calls = 0
        self._auth()

    def _auth(self):
        r = request("POST", "https://www.reddit.com/api/v1/access_token", session=self.s,
                    auth=(self.id, self.secret), data={"grant_type": "client_credentials"})
        tok = r.json().get("access_token")
        if not tok:
            raise ApiError(f"Reddit auth failed: {r.text[:200]}")
        self.s.headers["Authorization"] = f"bearer {tok}"
        self.token_expires = time.time() + r.json().get("expires_in", 3600) - 60

    def get(self, path, **params):
        if time.time() > self.token_expires:
            self._auth()
        r = request("GET", API + path, session=self.s, params={"raw_json": 1, **params})
        self.calls += 1
        # stay under the limit using Reddit's own counters
        remaining = float(r.headers.get("x-ratelimit-remaining", 100))
        reset = float(r.headers.get("x-ratelimit-reset", 0))
        if remaining < 5:
            log.info("reddit rate limit nearly used, pausing %.0fs", reset + 1)
            time.sleep(reset + 1)
        return r.json()

    def anon(self, name):
        if not name or name in ("[deleted]", "AutoModerator"):
            return name
        return "u_" + hashlib.sha256((self.salt + name).encode()).hexdigest()[:16]


def _ts(sec):
    return datetime.fromtimestamp(sec) if sec else None


def post_item(rd, d):
    return {
        "source": "reddit", "source_id": d["name"], "url": "https://www.reddit.com" + d["permalink"],
        "kind": "post", "community": d.get("subreddit"), "author": rd.anon(d.get("author")),
        "title": d.get("title"), "text": d.get("selftext") or None,
        "media_type": "text" if d.get("is_self") else (d.get("post_hint") or "link"),
        "published_at": _ts(d.get("created_utc")), "score": d.get("score"), "comments": d.get("num_comments"),
        "raw": {k: d.get(k) for k in ("id", "subreddit", "link_flair_text", "upvote_ratio", "over_18",
                                       "url", "domain", "is_self", "total_awards_received")},
    }


def comment_items(rd, children, post_fullname, sub, out):
    for c in children:
        if c.get("kind") != "t1":
            continue  # "more" stubs: skipped to stay within the request budget
        d = c["data"]
        out.append({
            "source": "reddit", "source_id": d["name"], "url": "https://www.reddit.com" + d.get("permalink", ""),
            "kind": "comment", "community": sub, "author": rd.anon(d.get("author")), "parent_id": post_fullname,
            "text": d.get("body"), "published_at": _ts(d.get("created_utc")), "score": d.get("score"),
            "raw": {"depth": d.get("depth"), "parent": d.get("parent_id")},
        })
        replies = d.get("replies")
        if isinstance(replies, dict):
            comment_items(rd, replies["data"]["children"], post_fullname, sub, out)


def listing(rd, path, max_items, **params):
    items, after = [], None
    while len(items) < max_items:
        data = rd.get(path, limit=min(100, max_items - len(items)), after=after, **params)["data"]
        items += [c["data"] for c in data["children"] if c["kind"] == "t3"]
        after = data.get("after")
        if not after:
            break
    return items


def run(con, cfg):
    started, errors, notes = datetime.now(), 0, []
    new = updated = snaps = 0
    try:
        rd = Reddit()
    except ApiError as e:
        store.log_run(con, "reddit", started, 0, 0, 0, 1, "skipped", str(e))
        log.error("reddit skipped: %s", e)
        return
    c = cfg["reddit"]
    seen = set()
    for sub in c["subreddits"]:
        try:
            posts = {p["name"]: p for p in listing(rd, f"/r/{sub}/new", c["new_posts_per_sub"])}
            posts.update({p["name"]: p for p in listing(rd, f"/r/{sub}/top", c["top_posts_per_sub"], t="day")})
            items = [post_item(rd, p) for p in posts.values()]
            for p in posts.values():
                if (p.get("score") or 0) >= c["comments_min_score"] and p.get("num_comments"):
                    try:
                        thread = rd.get(f"/r/{sub}/comments/{p['id']}", limit=c["comments_per_post"],
                                        depth=4, sort="top")
                        comment_items(rd, thread[1]["data"]["children"], p["name"], sub, items)
                    except ApiError as e:
                        errors += 1
                        notes.append(f"comments {p['name']}: {e}")
            n, u = store.save(con, items)
            new, updated, snaps = new + n, updated + u, snaps + len(items)
            seen.update(posts)
            log.info("reddit r/%s: %d posts, %d comments (%d new)", sub, len(posts), len(items) - len(posts), n)
        except ApiError as e:
            errors += 1
            notes.append(f"r/{sub}: {e}")
            log.error("reddit r/%s failed: %s", sub, e)

    # re-measure engagement on recent posts not already refreshed above
    stale = [i for i in store.recent_ids(con, "reddit", cfg["snapshots"]["window_days"], kind="post")
             if i not in seen]
    for k in range(0, len(stale), 100):
        try:
            data = rd.get("/api/info", id=",".join(stale[k:k + 100]))["data"]["children"]
            items = [post_item(rd, ch["data"]) for ch in data if ch["kind"] == "t3"]
            n, u = store.save(con, items)
            updated, snaps = updated + u, snaps + len(items)
        except ApiError as e:
            errors += 1
            notes.append(f"refresh batch {k}: {e}")
    status = "ok" if not errors else ("partial" if new or updated else "failed")
    store.log_run(con, "reddit", started, new, updated, snaps, errors, status,
                  f"{rd.calls} API calls. " + " | ".join(notes))
    log.info("reddit done: %d new, %d updated, %d snapshots, %d errors, %d calls", new, updated, snaps, errors, rd.calls)
