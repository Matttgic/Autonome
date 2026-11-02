"""Lecture SANS EXÉCUTION de l'état Nuxt embarqué (window.__NUXT__=(function(a,b,..){return {...}}(v1,v2,..))).

Analyseur de littéraux JavaScript (objets, tableaux, chaînes, nombres, booléens, null, void 0, références
aux paramètres). Tout autre code JS lève JsLitError : on ne tente jamais de l'interpréter.
"""
from __future__ import annotations

import json
import re


class JsLitError(ValueError):
    pass


MAX_ARRAY = 100_000
MAX_DEPTH = 200
MAX_INPUT = 8_000_000


_ID = re.compile(r"[A-Za-z_$][A-Za-z0-9_$]*")
_ACCESS = re.compile(r"\[(\d+)\]|\.([A-Za-z_$][\w$]*)|\[\"([^\"]*)\"\]")
_ASSIGN = re.compile(r"([A-Za-z_$][\w$]*)((?:\[\d+\]|\.[A-Za-z_$][\w$]*|\[\"[^\"]*\"\])+)=(?!=)")
_NUM = re.compile(r"-?(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?")


class _P:
    def __init__(self, s: str, env: dict | None = None):
        self.s, self.i, self.env = s, 0, env or {}

    def ws(self):
        while self.i < len(self.s) and self.s[self.i] in " \t\r\n":
            self.i += 1

    def peek(self):
        self.ws()
        return self.s[self.i] if self.i < len(self.s) else ""

    def eat(self, c):
        if self.peek() != c:
            raise JsLitError(f"attendu {c!r} à {self.i}: {self.s[self.i:self.i + 30]!r}")
        self.i += 1

    def string(self):
        q = self.s[self.i]
        j = self.i + 1
        buf = []
        while True:
            c = self.s[j]
            if c == "\\":
                nx = self.s[j + 1]
                if nx == "u":
                    buf.append(self.s[j:j + 6])
                    j += 6
                elif nx == "x":
                    buf.append("\\u00" + self.s[j + 2:j + 4])
                    j += 4
                elif nx == "'":
                    buf.append("'")
                    j += 2
                else:
                    buf.append(self.s[j:j + 2])
                    j += 2
                continue
            if c == q:
                break
            buf.append('\\"' if c == '"' else c)
            j += 1
        self.i = j + 1
        raw = "".join(buf)
        try:
            return json.loads('"' + raw + '"')
        except json.JSONDecodeError as e:
            raise JsLitError(f"chaîne invalide à {self.i}") from e

    def value(self):
        self.depth = getattr(self, "depth", 0) + 1
        if self.depth > MAX_DEPTH:
            raise JsLitError("imbrication trop profonde")
        try:
            return self._value()
        finally:
            self.depth -= 1

    def _value(self):
        c = self.peek()
        if c == "{":
            return self.obj()
        if c == "[":
            return self.arr()
        if c in "\"'":
            return self.string()
        m = _NUM.match(self.s, self.i)
        if m and (c.isdigit() or c in "-."):
            self.i = m.end()
            t = m.group()
            return float(t) if any(x in t for x in ".eE") else int(t)
        m = _ID.match(self.s, self.i)
        if m:
            name = m.group()
            self.i = m.end()
            if name == "true":
                return True
            if name == "false":
                return False
            if name in ("null", "undefined"):
                return None
            if name == "void":
                self.ws()
                self.value()
                return None
            if name == "Array" and self.peek() == "(":  # Array(n) : tableau vide de taille n
                self.eat("(")
                n = self.value()
                self.eat(")")
                if not isinstance(n, int) or not 0 <= n <= MAX_ARRAY:
                    raise JsLitError(f"Array({n}) hors bornes")
                return [None] * n
            if name in self.env:
                return self.env[name]
            raise JsLitError(f"identifiant inconnu {name!r} à {self.i}")
        raise JsLitError(f"valeur inattendue à {self.i}: {self.s[self.i:self.i + 30]!r}")

    def obj(self):
        self.eat("{")
        out = {}
        while self.peek() != "}":
            c = self.peek()
            if c in "\"'":
                k = self.string()
            else:
                m = _ID.match(self.s, self.i) or _NUM.match(self.s, self.i)
                if not m:
                    raise JsLitError(f"clé invalide à {self.i}")
                k, self.i = m.group(), m.end()
            self.eat(":")
            out[k] = self.value()
            if self.peek() == ",":
                self.i += 1
        self.eat("}")
        return out

    def arr(self):
        self.eat("[")
        out = []
        while self.peek() != "]":
            out.append(self.value())
            if self.peek() == ",":
                self.i += 1
        self.eat("]")
        return out


def _matching(s: str, i: int, o: str, c: str) -> int:
    """Index de la parenthèse/accolade fermante correspondant à s[i]==o (ignore les chaînes)."""
    depth, j, q = 0, i, None
    while j < len(s):
        ch = s[j]
        if q:
            if ch == "\\":
                j += 2
                continue
            if ch == q:
                q = None
        elif ch in "\"'":
            q = ch
        elif ch == o:
            depth += 1
        elif ch == c:
            depth -= 1
            if depth == 0:
                return j
        j += 1
    raise JsLitError("parenthésage non fermé")


def parse_nuxt(html: str) -> dict:
    """Toute erreur d'analyse devient JsLitError (jamais d'autre exception, jamais d'exécution)."""
    if len(html) > MAX_INPUT:
        raise JsLitError("page trop grande")
    try:
        return _parse_nuxt(html)
    except JsLitError:
        raise
    except (IndexError, KeyError, TypeError, ValueError, RecursionError, MemoryError, OverflowError) as e:
        raise JsLitError(f"{type(e).__name__}") from None


def _parse_nuxt(html: str) -> dict:
    k = html.find("window.__NUXT__=")
    if k < 0:
        raise JsLitError("pas d'état __NUXT__")
    s = html[k + len("window.__NUXT__="):]
    m = re.match(r"\(function\(([^)]*)\)\{", s)
    if not m:  # forme littérale directe
        return _P(s).value()
    params = [p.strip() for p in m.group(1).split(",") if p.strip()]
    body_start = m.end() - 1
    body_end = _matching(s, body_start, "{", "}")
    body = s[body_start + 1:body_end]
    if not s[body_end + 1:].startswith("("):
        raise JsLitError("appel de fonction attendu")
    args_end = _matching(s, body_end + 1, "(", ")")
    ap = _P("[" + s[body_end + 2:args_end] + "]")
    args = ap.value()
    env = dict(zip(params, args + [None] * (len(params) - len(args))))
    p = _P(body, env)
    # Seules des affectations déclaratives « a.b.c=valeur; » sont acceptées avant le return.
    while True:
        p.ws()
        if p.s.startswith("return ", p.i):
            p.i += len("return ")
            return p.value()
        m = _ASSIGN.match(p.s, p.i)
        if not m:
            raise JsLitError(f"instruction non déclarative à {p.i}: {p.s[p.i:p.i + 40]!r} (pas d'exécution)")
        p.i = m.end()
        target = env.get(m.group(1))
        keys = [int(a) if a else (b or c) for a, b, c in _ACCESS.findall(m.group(2))]
        for k in keys[:-1]:
            target = target[k] if isinstance(target, (dict, list)) else None
        if not isinstance(target, (dict, list)):
            raise JsLitError(f"cible non objet pour {m.group(0)}")
        if isinstance(target, list) and not 0 <= keys[-1] < MAX_ARRAY:
            raise JsLitError("indice hors bornes")
        if isinstance(target, list) and keys[-1] >= len(target):
            target.extend([None] * (keys[-1] + 1 - len(target)))
        target[keys[-1]] = p.value()
        if p.peek() == ";":
            p.i += 1
