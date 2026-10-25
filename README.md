# Pronostici Top 5

Sistema automatico di pronostici per Serie A, Premier League, LaLiga, Bundesliga e Ligue 1.
Gira da solo su GitHub ogni mattina e poi ogni ora, e pubblica i risultati su una pagina web.

**Pagina:** https://eremite1.github.io/pronostici-calcio/

## Cosa fa
- Calcola la forza di attacco e difesa di ogni squadra da expected goals e gol reali, con più peso alle partite recenti.
- Corregge i gol attesi per assenze (pesate sul contributo reale di ogni giocatore), meteo all'ora della partita e fattore campo.
- Li confronta e li avvicina alle quote medie reali dei bookmaker, quando disponibili.
- Con il modello di Poisson (correzione Dixon-Coles) calcola le probabilità di oltre 150 mercati: 1X2, doppia chance,
  Under/Over, Goal/No Goal, multigol totali, casa e ospite, gol per squadra, combo, primo tempo, pari/dispari e risultati esatti.
- Sceglie le combinazioni di 2-3 partite con quota tra 2 e 3 e la probabilità di vincita più alta.
- Salva ogni pronostico e lo verifica dopo la partita (pagina Storico).

## Fonti (gratuite, senza registrazione)
Understat (xG, giocatori, calendario) · football-data.co.uk (tiri, angoli, quote reali) · ESPN (stadio, possesso) ·
RotoWire (probabili formazioni e infortuni) · Fantacalcio.it (Serie A) · Open-Meteo (meteo).

## Struttura
- `src/` il programma
- `templates/` l'aspetto della pagina
- `docs/` la pagina pubblicata (creata automaticamente)
- `data/` storico dei pronostici e memoria dei dati già scaricati
- `.github/workflows/pronostici.yml` quando gira il programma
