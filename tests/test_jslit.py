import unittest

from autonome.sources.jslit import JsLitError, parse_nuxt


class JsLit(unittest.TestCase):
    def test_function_form_with_params_and_assignments(self):
        html = ('<script>window.__NUXT__=(function(a,b,c,d){d.x=a;d.l[1]=b;return {o:a,s:"A\\u002FB",n:-1.5e1,'
                'arr:[a,c,void 0,Array(2)],ref:d,"q k":true}}(2.37,"Nul",null,{l:[0,0]}));</script>')
        d = parse_nuxt(html)
        self.assertEqual(d["o"], 2.37)
        self.assertEqual(d["s"], "A/B")
        self.assertEqual(d["n"], -15.0)
        self.assertEqual(d["arr"], [2.37, None, None, [None, None]])
        self.assertEqual(d["ref"], {"l": [0, "Nul"], "x": 2.37})
        self.assertTrue(d["q k"])

    def test_refuses_code(self):
        for bad in ['window.__NUXT__=(function(a){alert(1);return {}}(1))',
                    'window.__NUXT__=(function(a){return {x:fetch("u")}}(1))']:
            with self.assertRaises(JsLitError):
                parse_nuxt(bad)

    def test_missing_state(self):
        with self.assertRaises(JsLitError):
            parse_nuxt("<html></html>")


if __name__ == "__main__":
    unittest.main()
