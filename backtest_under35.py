"""Backtest strategia 2: partite "da over" ma con squadre che segnano poco nel primo tempo.
Punto UNDER 3.5 prima della partita, cashout al minuto X se la quota e' scesa.

Come per il primo backtest e' una STIMA:
  - i dati gratuiti non hanno le quote dell'under 3.5: le ricavo dalle quote under/over 2.5
  - minuto dei gol del primo tempo stimato, quote al cashout calcolate con Poisson
"""
import os
from math import comb, exp, factorial
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from comune import (CAMPIONATI, scarica_storico, stagioni_recenti, pulisci, lambda_da_quote,
                    profitto_cashout, COMMISSIONE, MINUTI_TOTALI)
from squadre import Memoria

PUNTATA = 10.0
LINEA = 3            # under 3.5 = al massimo 3 gol
MEZZO_SPREAD = 1.01  # punto un po' sotto la quota giusta, banco un po' sopra
MINUTI = [10, 15, 20, 25]
FILTRI = [  # (nome, gol attesi minimi nella partita, gol attesi massimi nel 1T delle squadre)
    ("Tutte le partite", 0, 99),
    ("Partita da over (gol attesi ≥ 2.8)", 2.8, 99),
    ("Da over + 1T squadre ≤ 1.0 gol", 2.8, 1.0),
    ("Da over + 1T squadre ≤ 0.9 gol", 2.8, 0.9),
    ("Gol attesi ≥ 2.6 + 1T squadre ≤ 0.9", 2.6, 0.9),
    ("Gol attesi ≥ 2.6 + 1T squadre ≤ 0.8", 2.6, 0.8),
]


def p_max(lam, k):
    return sum(exp(-lam) * lam ** i / factorial(i) for i in range(k + 1))


def quota_giusta(lam, minuto, gol):
    if gol > LINEA:
        return 1000.0
    rimasti = lam * max(MINUTI_TOTALI - minuto, 0) / MINUTI_TOTALI
    return 1 / max(p_max(rimasti, LINEA - gol), 1e-3)


def esegui(df):
    mem, righe = Memoria(), []
    for r in df.itertuples():
        s = mem.stima(r.HomeTeam, r.AwayTeam)
        if s and pd.notna(r.QuotaUnder) and pd.notna(r.QuotaOver) and r.QuotaUnder > 1.01:
            lam = lambda_da_quote(r.QuotaUnder, r.QuotaOver)
            ingresso = quota_giusta(lam, 0, 0) / MEZZO_SPREAD
            k = r.HTHG + r.HTAG
            riga = {"Data": r.Data, "Div": r.Div, "Partita": f"{r.HomeTeam}-{r.AwayTeam}",
                    "GolAttesi": round(lam, 2), "Gol1T_squadre": s["gol_attesi_1T"],
                    "QuotaU35": round(ingresso, 2),
                    "fine": PUNTATA * (ingresso - 1) * (1 - COMMISSIONE)
                    if r.FTHG + r.FTAG <= LINEA else -PUNTATA}
            for m in MINUTI:
                p, tot = m / 45, 0.0
                for j in range(k + 1):    # j gol arrivati prima del cashout
                    prob = comb(k, j) * p ** j * (1 - p) ** (k - j)
                    uscita = quota_giusta(lam, m, j) * MEZZO_SPREAD
                    tot += prob * profitto_cashout(PUNTATA, ingresso, uscita)
                riga[f"cash{m}"] = tot
            righe.append(riga)
        mem.aggiungi(r)
    return pd.DataFrame(righe)


def riassunto(sel, col):
    n = len(sel)
    tot = sel[col].sum() if n else 0
    return {"Partite": n, "In verde %": round((sel[col] > 0).mean() * 100, 1) if n else 0,
            "Profitto €": round(tot, 2),
            "Rendimento %": round(tot / (n * PUNTATA) * 100, 2) if n else 0}


def tabella_md(righe):
    t = list(righe[0])
    return ("| " + " | ".join(t) + " |\n|" + "---|" * len(t) + "\n" +
            "".join("| " + " | ".join(str(r[c]) for c in t) + " |\n" for r in righe))


def main():
    locale = os.environ.get("DATI_LOCALI")
    if locale:
        df = pulisci(pd.concat([pd.read_csv(os.path.join(locale, f), encoding="latin-1")
                                .assign(Div=f.split("_")[0]) for f in os.listdir(locale)]))
    else:
        df = scarica_storico(stagioni_recenti(4))
    ris = esegui(df)
    os.makedirs("risultati", exist_ok=True)
    ris.to_csv("risultati/backtest_under35_dettaglio.csv", index=False)

    righe = []
    plt.figure(figsize=(9, 4.5))
    for nome, gmin, g1t in FILTRI:
        sel = ris[(ris.GolAttesi >= gmin) & (ris.Gol1T_squadre <= g1t)]
        for col, et in [(f"cash{m}", f"cashout al {m}'") for m in MINUTI] + [("fine", "tengo fino alla fine")]:
            righe.append({"Filtro": nome, "Uscita": et,
                          "Quota media": round(sel.QuotaU35.mean(), 2) if len(sel) else "-",
                          **riassunto(sel, col)})
        if len(sel):
            plt.plot(sel["Data"], sel["cash15"].cumsum(), label=nome)
    plt.axhline(0, color="grey", lw=0.8)
    plt.title(f"Under 3.5 con cashout al 15' – profitto cumulato (puntata {PUNTATA:.0f} €)")
    plt.ylabel("€"); plt.legend(fontsize=7); plt.tight_layout()
    plt.savefig("risultati/grafico_under35.png", dpi=110)

    testo = ["# Backtest – Under 3.5 su partite da over con primo tempo lento\n",
             f"Partite analizzate: **{len(ris)}**. Puntata {PUNTATA:.0f} €, commissione {int(COMMISSIONE*100)}%.\n",
             "**Gol attesi** = gol previsti dal mercato per la partita. "
             "**1T squadre** = gol medi nel primo tempo delle due squadre nelle ultime 10 partite.\n",
             tabella_md(righe), "\n![grafico](grafico_under35.png)\n",
             "> Stima: quote under 3.5, minuti dei gol e quote di cashout calcolati, non reali.\n"]
    open("risultati/BACKTEST_UNDER35.md", "w", encoding="utf-8").write("\n".join(testo))
    print("\n".join(testo))


if __name__ == "__main__":
    main()
