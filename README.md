# trendlab-reddit-collector

A small, read-only Reddit collector for a personal, non-commercial research project on how fashion trends
emerge and spread online. It counts how often styles (for example "wide leg jeans", "mary janes" or
"quiet luxury") come up in fashion communities over time, so they can be compared with Google search
interest and news coverage.

This repository contains only the code that talks to Reddit. It holds no collected data.

## What it does

- **Read-only.** It never posts, comments, votes or sends messages.
- **Once a day, about 100–200 requests in total**, well under the 100 requests/minute limit.
  - The newest ~300 posts and the day's top 100 posts from each configured subreddit (`/r/{sub}/new`, `/r/{sub}/top?t=day`).
  - Comments only on posts scoring 25 or more (`/r/{sub}/comments/{id}`).
  - Updated score and comment counts for posts from the last 14 days (`/api/info`, 100 ids per request).
- **Polite by default.** It sends a descriptive User-Agent, pauses when Reddit's `x-ratelimit-remaining` header runs low, and backs off exponentially on 429 and 5xx responses, honoring `Retry-After`.

## Privacy

- Usernames are never stored. Each author is replaced by a salted one-way hash (`collector/reddit.py`, `anon()`), so posts by the same person can be grouped without knowing who they are.
- Data is stored only in a local DuckDB file (`data/`, excluded from this repository).
- Data is used only for aggregate counts. It is not shared, sold, republished or used to train AI models.

## Subreddits

See `config/subreddits.yaml`: r/femalefashionadvice, r/malefashionadvice, r/fashion, r/OUTFITS,
r/RepLadies, r/frugalmalefashion, r/VintageFashion.

## Files

| File | Purpose |
|---|---|
| `collector/reddit.py` | App-only OAuth, listing/comment requests, author anonymization |
| `collector/http.py` | Retries with exponential backoff; honors `Retry-After` |
| `collector/store.py` | Deduplicated storage (one row per post/comment) plus engagement snapshots |
| `collector/db.py` | Local DuckDB schema |
| `collect.py` | Runs one collection |

## Running

```bash
pip3 install -r requirements.txt
cp .env.example .env   # add Reddit app credentials and a random AUTHOR_HASH_SALT
python3 collect.py
```
