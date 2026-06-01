# SniperBot ICT — Design Document

## Overview

SniperBot è un servizio headless che monitora il NASDAQ 100 (NQ Futures) durante la killzone 13:30-15:30 GMT e apre operazioni basate sulla strategia ICT, con esecuzione diretta via Interactive Brokers.

## Stack

- **Linguaggio**: Python 3.11+
- **Broker/Data**: Interactive Brokers (IB Gateway + `ib_insync`)
- **Strumento**: NQ Futures (E-mini NASDAQ-100, CME), 1 contratto. Tick size: 0.25 punti ($5/tick). Leva ~20:1 intraday.
- **Deployment**: Macchina locale, schedulato solo durante killzone
- **Esecuzione**: Live diretta, no backtesting

## Struttura del progetto

```
Sniperbot2/
├── sniperbot/
│   ├── __init__.py
│   ├── main.py                 # Entry point, scheduler killzone, loop principale
│   ├── config.py               # Costanti e parametri configurabili
│   ├── data/
│   │   ├── __init__.py
│   │   └── ib_client.py        # IB Gateway + ib_insync: fetch M5/M1, ordini, stato account
│   ├── strategy/
│   │   ├── __init__.py
│   │   ├── swing_points.py     # Rilevazione swing point M5 (5L/3R, ≥100 tick)
│   │   ├── fvg.py              # Fair Value Gap detection e tracking senza scadenza
│   │   ├── zonation.py         # Premium / Discount determination
│   │   ├── confirmation.py     # Conferma M1 2/3
│   │   └── targets.py          # TP multi-livello liquidità, filtro 40 tick
│   ├── execution/
│   │   ├── __init__.py
│   │   ├── order_manager.py    # Entry, trailing SL, gestione TP
│   │   └── risk_manager.py     # Max daily loss gate (5-10%)
│   └── logs/                   # Log trade giornalieri
├── tests/                      # Test per modulo
├── requirements.txt
└── README.md
```

## Moduli e responsabilità

| Modulo | Responsabilità |
|--------|---------------|
| `ib_client` | Connessione IB Gateway, fetch candele M5/M1, invio/modifica ordini futures, recupero stato account e posizioni |
| `swing_points` | Rilevazione swing point M5: finestra 5 barre sinistra / 3 destra, escursione minima 100 tick NQ (25 punti indice) |
| `fvg` | Rilevazione Fair Value Gap su 300 candele M5. Tracking senza scadenza: FVG rimosso solo quando prezzo chiude completamente il gap |
| `zonation` | Determina se prezzo è in Premium (solo SHORT) o Discount (solo LONG) usando swing point significativi e calcolo 50% range |
| `confirmation` | Passa a M1, attende 3 candele, applica regola 2/3: ≥2 bullish → LONG, ≥2 bearish → SHORT |
| `targets` | Calcola TP multi-livello: high/low Asia, London, NY precedente, same highs/lows, swing M5. Filtra a ≥40 tick dall'entry, ordinati per distanza |
| `order_manager` | Entry all'open della 4ª M1, SL iniziale al penultimo swing point, trailing SL su nuovi swing point, uscita TP progressiva |
| `risk_manager` | Blocco operatività se loss giornaliero ≥8% equity. 1 contratto NQ fisso, no scaling |

## Flusso di esecuzione

```
SCHEDULER: avvia bot 15:30, ferma 17:30 ora italiana (solo feriali)
                          │
1. FETCH ──────────────── 300 M5 + M1 recenti da IB Gateway
2. SWING POINTS ───────── Detection su M5 (5L/3R, ≥100 tick)
3. ZONATION ───────────── Premium o Discount?
4. FVG ────────────────── Detection su 300 M5, tracking FVG attivi
5. MATCH ──────────────── M5 close dentro FVG + direzione FVG matcha zona?
                          ├─ NO → skip ciclo
                          └─ SI ↓
6. M1 WAIT ────────────── Attendi prossime 3 candele M1
7. 2/3 CHECK ──────────── ≥2/3 M1 confermano direzione?
                          ├─ NO → nessuna entry
                          └─ SI ↓
8. ENTRY ──────────────── All'open della 4ª M1, 1 contratto NQ
9. SL ─────────────────── SL iniziale = penultimo swing point
10. MONITOR ────────────── Trailing SL su nuovi swing point
                           TP a livelli liquidità (min 40 tick)
```

## Regole ICT dettagliate

### Killzone
- 13:30-15:30 GMT (15:30-17:30 Italia)
- Solo giorni feriali
- Bot schedulato per avviarsi e fermarsi automaticamente

### Premium / Discount
- Premium: prezzo sotto swing High ma sopra 50% del range (High → punto più basso dello swing low). Solo SHORT.
- Discount: prezzo sopra swing Low ma sotto 50% del range (Low → punto più alto dello swing high). Solo LONG.
- Dinamico: nuovi swing point ridefiniscono le zone.

### FVG (Fair Value Gap)
- Bullish FVG: `low[i] > high[i+2]` → gap tra `high[i+2]` e `low[i]`
- Bearish FVG: `high[i] < low[i+2]` → gap tra `high[i]` e `low[i+2]`
- Lookback: 300 candele M5
- Nessuna scadenza: FVG valido finché il prezzo non chiude completamente il gap
- Un FVG è "attivo" se il prezzo ha chiuso dentro la sua zona

### Conferma M1 2/3
- Dopo close M5 dentro FVG con direzione corretta
- Attendi 3 candele M1 successive
- ≥2 bullish → LONG; ≥2 bearish → SHORT
- Entry all'open della 4ª candela M1

### Stop Loss Trailing
- Iniziale: penultimo swing point prima dell'entry
- LONG: ogni nuovo swing low → SL spostato sotto nuovo swing low
- SHORT: ogni nuovo swing high → SL spostato sopra nuovo swing high

### Take Profit
Target multipli in ordine di vicinanza:
1. High/Low sessione Asiatica (00:00-09:00 GMT)
2. High/Low sessione Londra (09:00-11:00 GMT)
3. High/Low precedente sessione New York (giorno prima)
4. Same Highs / Same Lows (livelli con reazioni multiple)
5. Swing high/low significativi M5 (≥40 tick dall'entry)

Filtro obbligatorio: ogni target ≥40 tick dall'entry.

## Configurazione

```python
# trading
SYMBOL = "NQ"
POSITION_SIZE = 1

# killzone (ora italiana)
KILLZONE_START = "15:30"
KILLZONE_END = "17:30"

# swing points
SWING_WINDOW_LEFT = 5
SWING_WINDOW_RIGHT = 3
MIN_SWING_EXCURSION_TICKS = 100  # 25 punti indice NASDAQ

# FVG
FVG_LOOKBACK_CANDLES = 300

# conferma M1
M1_CONFIRMATION_BARS = 3
M1_BULLISH_NEEDED = 2
M1_BEARISH_NEEDED = 2

# take profit
MIN_TP_DISTANCE_TICKS = 40

# risk
MAX_DAILY_LOSS_PCT = 0.08  # 8%

# sessioni (GMT)
ASIA_START = "00:00"
ASIA_END = "09:00"
LONDON_START = "09:00"
LONDON_END = "11:00"
```

## Error Handling

| Scenario | Comportamento |
|----------|--------------|
| IB Gateway disconnesso/timeout | Retry exponential backoff 1s→2s→4s, max 3 tentativi. Falliti tutti: logga, skip ciclo |
| Connessione persa a trade aperto | Riconnette e recupera stato posizione da IB Gateway (non da stato locale) |
| Dati insufficienti (<300 M5) | Skip ciclo, log warning |
| Ordine rifiutato | Logga motivo. Errore fatale (margin) → stop giornata. Transiente → riprova |
| Nessuno swing point valido | Nessuna entry possibile, skip ciclo |
| Max daily loss raggiunto | Blocco nuove entry, chiusura posizioni aperte, solo monitoraggio passivo |

## Gestione stato

- **Senza stato persistente tra sessioni**: il bot è stateless tra una killzone e l'altra. Ogni sessione parte pulita.
- **Recupero posizione**: se il bot si riavvia con una posizione aperta su IB, la recupera e riprende il monitoraggio.
- **Log**: ogni evento (segnale, entry, SL modificato, TP, errori) scritto su file di log giornaliero in `logs/YYYY-MM-DD.log`.

## Test

| Tipo | Cosa testa |
|------|-----------|
| Unit: swing_points | Detection con OHLCV noti, filtro 100 tick, finestra 5L/3R |
| Unit: fvg | Pattern bullish/bearish, chiusura totale vs parziale, persistenza multi-candela |
| Unit: zonation | Premium/discount con swing mock, edge case 50% esatto |
| Unit: confirmation | 8 combinazioni 3 M1, verifica soglia 2/3 per entrambe le direzioni |
| Unit: targets | Session high/low mock, filtro 40 tick, ordinamento distanza |
| Unit: risk_manager | Daily loss trigger, blocco entry, calcolo P&L |
| Integration | Catena completa con dati storici: fetch → signal → entry simulata |
