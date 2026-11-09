"""État sur la branche data (lot AU-L1, 09/11/2026) : lecture tolérante, écritures atomiques, UTF-8, rotation en
archives gz sans perte, taille des fichiers, statut « à régler ». Lignes au FORMAT réel (champs de runs.jsonl,
observations.jsonl, bets.jsonl), valeurs synthétiques : aucune vraie cote ni vrai résultat."""
import gzip
import json
import tempfile
import unittest
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

from autonome import cli, consensus as CS, live, site, store, tracker
from autonome.sources import livescore as LS
from tests.test_livescore import SOCCER, bet as cbet

NOW = datetime(2026, 12, 20, 12, 0, tzinfo=timezone.utc)


def lines(p: Path) -> list[str]:
    return [x for x in p.read_text(encoding="utf-8").split("\n") if x.strip()]


def archived(root, stem) -> list[str]:
    out = []
    for p in sorted(Path(root, "archives").glob(f"{stem}-*.jsonl.gz")):
        out += [x for x in gzip.decompress(p.read_bytes()).decode("utf-8").split("\n") if x.strip()]
    return out


class TolerantRead(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()
        store.BAD.clear()

    def test_truncated_last_line_is_ignored_counted_and_quarantined(self):
        p = Path(self.d, "runs.jsonl")
        p.write_bytes(b'{"at": "2026-11-09T00:50:32+00:00", "errors": []}\n{"at": "2026-11-09T00:5')  # timeout au milieu
        self.assertEqual(store.read(self.d, "runs.jsonl"), [{"at": "2026-11-09T00:50:32+00:00", "errors": []}])
        self.assertEqual(store.BAD, {"runs.jsonl": 1})
        q = store.read(self.d, store.QUARANTINE)
        self.assertEqual([(x["fichier"], x["ligne"]) for x in q], [("runs.jsonl", '{"at": "2026-11-09T00:5')])
        store.read(self.d, "runs.jsonl")  # relue : pas mise deux fois en quarantaine
        self.assertEqual(len(store.read(self.d, store.QUARANTINE)), 1)
        self.assertEqual(store.BAD, {"runs.jsonl": 1})

    def test_middle_bad_and_non_object_lines(self):
        Path(self.d, "bets.jsonl").write_text('{"bet_id": "a"}\n{oups\n[1, 2]\n\n{"bet_id": "b"}\n', encoding="utf-8")
        self.assertEqual([r["bet_id"] for r in store.read(self.d, "bets.jsonl")], ["a", "b"])
        self.assertEqual(store.BAD["bets.jsonl"], 2)
        # réécrit sans les lignes illisibles (comme update_closing), mais elles restent en quarantaine
        store.write_all(self.d, "bets.jsonl", store.read(self.d, "bets.jsonl"))
        self.assertEqual({x["ligne"] for x in store.read(self.d, store.QUARANTINE)}, {"{oups", "[1, 2]"})

    def test_append_after_partial_line_never_glues_rows(self):
        p = Path(self.d, "lag.jsonl")
        p.write_bytes(b'{"at": "2026-11-08T10:00:00+00:00"}\n{"at": "2026-11')
        store.append(self.d, "lag.jsonl", [{"at": "2026-11-09T10:00:00+00:00"}])
        self.assertEqual([r["at"] for r in store.read(self.d, "lag.jsonl")],
                         ["2026-11-08T10:00:00+00:00", "2026-11-09T10:00:00+00:00"])
        self.assertTrue(p.read_bytes().endswith(b"\n"))

    def test_append_is_atomic(self):
        store.write_all(self.d, "observations.jsonl", [{"at": "2026-11-08T10:00:00+00:00", "n": 1}])
        before = Path(self.d, "observations.jsonl").read_bytes()
        with mock.patch("autonome.store.os.replace", side_effect=OSError("disque plein")):
            with self.assertRaises(OSError):
                store.append(self.d, "observations.jsonl", [{"at": "2026-11-09T10:00:00+00:00", "n": 2}])
        self.assertEqual(Path(self.d, "observations.jsonl").read_bytes(), before)  # ancien fichier intact

    def test_utf8_and_line_separators(self):
        row = {"home": "Bodø/Glimt", "away": "Ümraniye Spor\x85", "label": "Vainqueur : Ż"}
        store.append(self.d, "bets.jsonl", [row])
        self.assertEqual(store.read(self.d, "bets.jsonl"), [row])  # U+2028 ne coupe pas la ligne
        self.assertIn("Bodø".encode("utf-8"), Path(self.d, "bets.jsonl").read_bytes())  # UTF-8 quelle que soit la locale
        self.assertEqual(store.BAD, {})

    def test_tmp_name_keeps_gz_suffix(self):
        self.assertEqual(store._tmp(Path("archives/observations-2026-11.jsonl.gz")).name,
                         "observations-2026-11.jsonl.gz.tmp")


def runs_rows(start: datetime, days: int, every_h: float = 6) -> list[dict]:
    out, t = [], start
    while t < start + timedelta(days=days):
        out.append({"at": t.isoformat(), "mode": "live", "errors": ["kambi pmusportsfr betoffer/group/1.json: HTTP 404"]})
        t += timedelta(hours=every_h)
    return out


class Rotation(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()
        store.BAD.clear()

    def test_keeps_recent_days_and_loses_nothing(self):
        rows = runs_rows(datetime(2026, 10, 25, tzinfo=timezone.utc), 57)  # 25/10 -> 20/12
        store.write_all(self.d, "runs.jsonl", rows)
        p = Path(self.d, "runs.jsonl")
        orig = lines(p)
        n = store.rotate(self.d, "runs.jsonl", NOW, keep_days=14)
        hot = lines(p)
        self.assertEqual(n, len(orig) - len(hot))
        self.assertTrue(all(json.loads(x)["at"] >= (NOW - timedelta(days=14)).isoformat() for x in hot))
        self.assertEqual(Counter(hot + archived(self.d, "runs")), Counter(orig))  # chaud + archives = original
        self.assertEqual(sorted(x.name for x in Path(self.d, "archives").iterdir()),
                         ["runs-2026-10.jsonl.gz", "runs-2026-11.jsonl.gz", "runs-2026-12.jsonl.gz"])
        self.assertEqual(store.rotate(self.d, "runs.jsonl", NOW, keep_days=14), 0)  # rien à refaire
        # le lendemain : moins d'un jour de plus que la limite -> pas de rotation (au plus une par jour)
        self.assertEqual(store.rotate(self.d, "runs.jsonl", NOW + timedelta(hours=20), keep_days=14), 0)
        self.assertGreater(store.rotate(self.d, "runs.jsonl", NOW + timedelta(days=2), keep_days=14), 0)
        self.assertEqual(Counter(lines(p) + archived(self.d, "runs")), Counter(orig))
        self.assertEqual(store.read(self.d, "runs.jsonl")[0]["mode"], "live")

    def test_crash_between_archive_and_hot_rewrite_does_not_duplicate(self):
        store.write_all(self.d, "lag.jsonl", runs_rows(datetime(2026, 11, 1, tzinfo=timezone.utc), 49))
        orig = lines(Path(self.d, "lag.jsonl"))
        real = store.replace_bytes

        def fail_on_hot(p, data):
            if Path(p).name == "lag.jsonl":
                raise OSError("runner arrêté")
            real(p, data)
        with mock.patch("autonome.store.replace_bytes", side_effect=fail_on_hot):
            with self.assertRaises(OSError):
                store.rotate(self.d, "lag.jsonl", NOW, keep_days=30)
        self.assertEqual(lines(Path(self.d, "lag.jsonl")), orig)  # chaud intact
        store.rotate(self.d, "lag.jsonl", NOW, keep_days=30)       # passage suivant
        self.assertEqual(Counter(lines(Path(self.d, "lag.jsonl")) + archived(self.d, "lag")), Counter(orig))

    def test_size_cap_and_undated_lines(self):
        big = "x" * 900
        rows = [{"at": (NOW - timedelta(hours=i)).isoformat(), "pad": big} for i in range(200, 0, -1)]
        store.write_all(self.d, "observations.jsonl", rows)
        p = Path(self.d, "observations.jsonl")
        with p.open("a", encoding="utf-8") as f:
            f.write('{"sans_date": 1}\n')
        orig = lines(p)
        n = store.rotate(self.d, "observations.jsonl", NOW, keep_days=30, max_bytes=100_000, target_bytes=60_000)
        self.assertGreater(n, 0)
        self.assertLessEqual(p.stat().st_size, 60_000)
        self.assertIn('{"sans_date": 1}', lines(p))  # sans date lisible : reste dans le fichier chaud
        self.assertEqual(Counter(lines(p) + archived(self.d, "observations")), Counter(orig))

    def test_oversized(self):
        Path(self.d, "a.jsonl").write_bytes(b"x" * 30)
        Path(self.d, ".git").mkdir()
        Path(self.d, ".git", "pack").write_bytes(b"x" * 300)
        self.assertEqual(store.oversized(self.d, limit=20), [("a.jsonl", 30)])

    def test_housekeeping_reports_without_raising(self):
        store.write_all(self.d, "runs.jsonl", runs_rows(datetime(2026, 11, 20, tzinfo=timezone.utc), 30))
        Path(self.d, "bets.jsonl").write_text('{"bet_id": "a", "status": "open"}\n{"bet_', encoding="utf-8")
        store.read(self.d, "bets.jsonl")
        errors = []
        with mock.patch.object(cli, "STATE_MAX_BYTES", 1000):
            moved = cli.housekeeping(self.d, NOW, errors)
        self.assertEqual(set(moved), {"runs.jsonl"})
        self.assertTrue(any("illisible" in e and "bets.jsonl" in e for e in errors))
        self.assertTrue(any(e.startswith("état : runs.jsonl pèse") for e in errors))
        with mock.patch("autonome.store.rotate", side_effect=RuntimeError("archive incomplète")):
            errors = []
            self.assertEqual(cli.housekeeping(self.d, NOW, errors), {})
        self.assertTrue(errors and all(e.startswith("rotation ") for e in errors))


class ARegler(unittest.TestCase):
    def b(self, **k):
        r = {"bet_id": "x", "event_id": "e", "status": "open", "ref_kind": "consensus-anj", "commence": "2026-11-07T15:00:00Z",
             "odds": 2.0, "stake": 1.0, "ev": 0.05, "result": None, "close": None, "found_at": "2026-11-07T10:00:00+00:00"}
        r.update(k)
        return r

    def test_status_after_48h(self):
        start = datetime(2026, 11, 7, 15, 0, tzinfo=timezone.utc)
        self.assertFalse(tracker.a_regler(self.b(), start + timedelta(hours=47)))
        self.assertTrue(tracker.a_regler(self.b(), start + timedelta(hours=49)))
        self.assertFalse(tracker.a_regler(self.b(reporte="LiveScore 4 (Postp.)"), start + timedelta(hours=49)))
        self.assertFalse(tracker.a_regler(self.b(status="settled"), start + timedelta(hours=49)))
        self.assertFalse(tracker.a_regler(self.b(commence="??"), start + timedelta(hours=49)))

    def test_counted_apart_in_stats_and_site(self):
        d = tempfile.mkdtemp()
        later = datetime(2026, 11, 9, 16, 0, tzinfo=timezone.utc)
        store.write_all(d, tracker.BETS, [self.b(bet_id="old"), self.b(bet_id="new", commence="2026-11-09T18:00:00Z"),
                                          self.b(bet_id="won", status="settled", result={"won": True})])
        st = tracker.stats(d, later)
        self.assertEqual((st["bets_open"], st["bets_a_regler"], st["bets_settled"]), (1, 1, 1))
        self.assertEqual(st["roi"]["n"], 1)  # le pari à régler n'entre pas dans le ROI
        out = site.build(d, {"errors": []}, {}, later)
        self.assertEqual(out["bilan"]["a_regler"], 1)
        self.assertEqual({h["etat"] for h in out["historique"]}, {"à régler", "en cours", "gagné"})

    def test_postponed_marks(self):
        res = LS.parse(SOCCER, "FOOTBALL")
        rows = [cbet("Epsilon", "Zeta", "1x2", "home", "2026-11-02T18:00:00Z")]
        self.assertEqual(CS.settle(rows, res, datetime(2026, 11, 3, 12, 0, tzinfo=timezone.utc)), 0)
        self.assertEqual(rows[0]["reporte"], "LiveScore 4 (Postp.)")
        self.assertEqual(rows[0]["status"], "open")
        # Polymarket annonce un début décalé de plus de 3 h : signalé reporté, clôture mesurée sur le nouvel horaire
        d = tempfile.mkdtemp()
        store.write_all(d, tracker.BETS, [self.b(ref_kind="polymarket", event_id="pm|k", group="1x2", selection="home",
                                                 commence="2026-11-08T15:00:00Z")])
        ref = [{"key": "pm|k", "commence": "2026-11-09T15:00:00Z", "markets": {"1x2": {"home": {"p": 0.5, "spread": 0.02}}}}]
        live.update_closing(d, ref, datetime(2026, 11, 9, 14, 0, tzinfo=timezone.utc))
        r = store.read(d, tracker.BETS)[0]
        self.assertEqual(r["reporte"], "2026-11-09T15:00:00Z")
        self.assertFalse(tracker.a_regler(r, datetime(2026, 11, 11, tzinfo=timezone.utc)))


if __name__ == "__main__":
    unittest.main()
