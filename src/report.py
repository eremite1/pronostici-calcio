"""Crea la pagina web (cartella docs/, pubblicata da GitHub Pages)."""
import json
import os

from jinja2 import Environment, FileSystemLoader, select_autoescape

from . import config


def pct(x, d=0):
    return "–" if x is None else f"{x * 100:.{d}f}%"


def num(x, d=2):
    return "–" if x is None else f"{x:.{d}f}"


def rng(r):
    if not r:
        return "–"
    lo, hi, p = r
    return (f"{lo}" if lo == hi else f"{lo}-{hi}") + f" gol ({p * 100:.0f}%)"


FAMILY_ORDER = ["1X2", "Doppia chance", "Under/Over", "Goal/No Goal", "Multigol", "Multigol casa",
                "Multigol ospite", "Gol casa", "Gol ospite", "Combo", "1° tempo", "Pari/Dispari"]


def grouped(markets):
    out = {}
    for m in markets:
        out.setdefault(m["fam"], []).append(m)
    return [(f, out[f]) for f in FAMILY_ORDER if f in out]


STATUS_IT = {"OUT": "out", "QUES": "in dubbio", "SQUAL": "squalificato", "SUS": "squalificato",
             "SUSP": "squalificato", "GTD": "in dubbio", "DTD": "in dubbio"}


def render(ctx):
    env = Environment(loader=FileSystemLoader(config.TEMPLATES), autoescape=select_autoescape(["html"]))
    env.filters.update(pct=pct, num=num, rng=rng, grouped=grouped,
                       status=lambda s: STATUS_IT.get(str(s).upper(), str(s).lower()))
    os.makedirs(os.path.join(config.DOCS, "data"), exist_ok=True)
    for name in ("index.html", "storico.html"):
        html = env.get_template(name + ".j2").render(**ctx)
        with open(os.path.join(config.DOCS, name), "w", encoding="utf-8") as f:
            f.write(html)
    open(os.path.join(config.DOCS, ".nojekyll"), "w").close()
    light = dict(generated=ctx["generated"], slips_day=ctx["slips_day"], slips_window=ctx["slips_window"],
                 best=[{k: v for k, v in b.items()} for b in ctx["best"]],
                 matches=[dict(id=m["id"], league=m["league"], home=m["home"], away=m["away"],
                               kickoff=m["kickoff_utc"], lh=m["lh"], la=m["la"], p1x2=m["p1x2"],
                               top=[dict(name=t["name"], p=t["p"], odds=t["used"]) for t in m["top"]])
                          for m in ctx["matches"]])
    with open(os.path.join(config.DOCS, "data", "latest.json"), "w", encoding="utf-8") as f:
        json.dump(light, f, ensure_ascii=False, indent=1, default=str)
