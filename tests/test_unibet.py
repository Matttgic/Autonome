import unittest

from autonome.sources import unibet as ub

PAGE = ('<script type="application/ld+json">[{"@type":"SportsEvent","startDate":"2026-11-02T20:45:00",'
        '"url":"https://www.unibet.fr/paris-football/france/l1/3391164/alpha-vs-beta"},'
        '{"@type":"SportsEvent","startDate":"2026-11-02T21:00:00","url":"https://www.unibet.fr/paris-football/x/y/9/c-vs-d"}]</script>'
        '<div class="psel-event"><a class="psel-event__link" title="x" href="/paris-football/france/l1/3391164/alpha-vs-beta">'
        '<!----><p class="psel-event-info__competition">Ligue 1</p><span class="psel-opponent__name">Alpha</span>'
        '<span class="psel-opponent__name">Beta</span></a><table class="psel-market psel-market--row-col">'
        '<span class="psel-outcome__label">Alpha</span><span class="psel-outcome__data">2,30</span>'
        '<span class="psel-outcome__label">N</span><!----><span class="psel-outcome__data">3,00</span>'
        '<span class="psel-outcome__label">Beta</span><span class="psel-outcome__data">-</span></table></div>'
        '<div class="psel-event"><a class="psel-event__link" href="/paris-football/x/y/9/c-vs-d">'
        '<span class="psel-opponent__name">C</span><span class="psel-opponent__name">D</span></a>'
        '<table class="psel-market"><span class="psel-outcome__label">Plus</span><span class="psel-outcome__data">1,90</span>'
        '<span class="psel-outcome__label">Moins</span><span class="psel-outcome__data">1,85</span></table></div>')


class Unibet(unittest.TestCase):
    def test_parse(self):
        evs = ub.parse_page(PAGE)
        self.assertEqual(len(evs), 1)                      # le 2e bloc n'est pas un 1X2 : ignoré
        e = evs[0]
        self.assertEqual(e["commence"], "2026-11-02T19:45:00Z")  # 20:45 Paris (heure d'hiver) = 19:45 UTC
        self.assertEqual(e["odds"]["1x2"], {"home": 2.30, "draw": 3.00})  # « - » absent
        self.assertEqual(e["id"], "ub|3391164")
        self.assertTrue(e["url"].startswith("https://www.unibet.fr/"))


if __name__ == "__main__":
    unittest.main()
