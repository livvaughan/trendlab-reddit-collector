"""Run the Reddit collector once.   python3 collect.py

Settings: config/subreddits.yaml. Credentials: .env (see .env.example). Logs: logs/.
"""
import logging
import os
import sys
from datetime import date

import yaml

from collector import db, reddit


def main():
    os.makedirs(os.path.join(db.ROOT, "logs"), exist_ok=True)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s",
                        handlers=[logging.FileHandler(os.path.join(db.ROOT, "logs", f"reddit_{date.today()}.log")),
                                  logging.StreamHandler(sys.stdout)])
    cfg = yaml.safe_load(open(os.path.join(db.ROOT, "config", "subreddits.yaml")))
    con = db.connect()
    reddit.run(con, cfg)
    print(con.execute("SELECT status, new_items, updated, errors, left(note, 120) FROM collector_runs "
                      "ORDER BY started_at DESC LIMIT 1").fetchall())
    con.close()


if __name__ == "__main__":
    main()
