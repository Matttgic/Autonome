import json
import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

from autonome import cli, oddsapi, store, tracker


def raw_event():
    st = (datetime.now(timezone.utc) + timedelta(hours=6)).strftime("%Y-%m-%dT%H:%M:%SZ")
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    mk = lambda a, b: [{"key": "h2h", "outcomes": [{"name": "A", "price": a}, {"name": "B", "price": b}]}]
    return {"id": "ev1", "sport_key": "tennis_x", "commence_time": st, "home_team": "A", "away_team": "B",
            "bookmakers": [{"key": "pinnacle", "title": "P", "last_update": now, "markets": mk(1.90, 2.00)},
                           {"key": "winamax_fr", "title": "W", "last_update": now, "markets": mk(2.10, 1.80)}]}


class FakeClient:
    remaining = 400
    def __init__(self, *a, **k): pass
    def sports(self): return [{"key": "tennis_x", "active": True}]
    def odds(self, *a, **k): return [raw_event()]


class E2E(unittest.TestCase):
    def test_scan_end_to_end(self):
        d = tempfile.mkdtemp()
        os.chdir(Path(__file__).resolve().parent.parent)
        cfgp = Path(d, "c.json")
        cfgp.write_text(json.dumps({"markets": "h2h", "regions": "eu", "sports_priority": ["tennis_x"],
                                    "credits_per_scan": 3, "credits_reserve": 10, "credits_per_close": 3,
                                    "credits_per_settle": 3, "engine": {}}))
        with mock.patch.object(oddsapi, "Client", FakeClient), mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("NTFY_TOPIC", None)
            rc = cli.main(["scan", "--state", d + "/s", "--out", d + "/site", "--config", str(cfgp)])
        self.assertEqual(rc, 0)
        bets = store.read(d + "/s", tracker.BETS)
        self.assertEqual(len(bets), 1)
        self.assertEqual(bets[0]["book"], "winamax_fr")
        self.assertIn("Winamax".lower(), Path(d, "site/index.html").read_text().lower().replace("winamax_fr", "winamax"))
        # 2e scan : pas de doublon
        with mock.patch.object(oddsapi, "Client", FakeClient):
            cli.main(["scan", "--state", d + "/s", "--out", d + "/site", "--config", str(cfgp)])
        self.assertEqual(len(store.read(d + "/s", tracker.BETS)), 1)


if __name__ == "__main__":
    unittest.main()
