# Spot Price Fetcher

Služba, která stahuje 15minutové spotové ceny elektřiny z denního trhu [OTE-ČR](https://www.ote-cr.cz/cs/kratkodobe-trhy/elektrina/denni-trh), přepočítá je z EUR na CZK podle aktuálního kurzu [ČNB](https://api.cnb.cz/) a uloží je přes [PostgREST](https://postgrest.org/) API do databáze.

## Jak to funguje

1. Po spuštění hned provede první stažení dat.
2. Potom běží v nekonečné smyčce a stahuje data každý den v **00:00**.
3. Každé stažení:
   - načte data grafu z `https://www.ote-cr.cz/cs/kratkodobe-trhy/elektrina/denni-trh/chart-data`,
   - vybere řadu **„15min cena (EUR/MWh)“** (96 period za den) a z titulku grafu přečte datum,
   - stáhne denní kurz EUR/CZK z `https://api.cnb.cz/cnbapi/exrates/daily`,
   - převede periody 1–96 na časy `00:00`–`23:45` a ke každé ceně dopočítá cenu v CZK,
   - pošle výsledek metodou `POST` na `{POSTGREST_URL}/rpc/insert_spot_price`.
4. Když dojde k neočekávané chybě, počká minutu a zkusí to znovu.

## Požadavky

- Docker a Docker Compose, **nebo**
- Python 3.11+ (spouštění bez Dockeru)
- Běžící PostgREST s RPC funkcí `insert_spot_price` (viz [Formát dat](#formát-dat))

## Konfigurace

Konfigurace se zadává přes proměnné prostředí, nejpohodlněji v souboru `.env` v kořeni projektu (soubor je v `.gitignore`):

```env
POSTGREST_URL=http://localhost:3000
POSTGREST_API_KEY=your_api_key_here
```

| Proměnná            | Povinná | Popis                                                        |
|---------------------|---------|--------------------------------------------------------------|
| `POSTGREST_API_KEY` | ano     | API klíč, posílá se v hlavičce `x-api-key`                   |
| `POSTGREST_URL`     | ne      | Základní URL PostgREST API (výchozí hodnota viz níže)        |

> **Výchozí `POSTGREST_URL`:** `docker-compose.yml` a `run.sh` použijí `http://localhost:3000`. Pokud skript spustíte přímo bez nastavené proměnné, použije `http://postgrestapi:3000`.

## Spuštění

### Docker Compose (doporučeno)

```bash
docker compose up -d --build
docker compose logs -f spot_container
```

Kontejner má nastavené `restart: unless-stopped`.

> **Pozor:** uvnitř kontejneru `localhost` ukazuje na kontejner samotný, ne na hostitele. Pokud PostgREST běží v jiném kontejneru, nastavte `POSTGREST_URL` na jméno jeho služby (např. `http://postgrestapi:3000`) a připojte obě služby do stejné sítě. V `docker-compose.yml` je k tomu připravená zakomentovaná sekce `networks`.

> **Časové pásmo:** spouštění „o půlnoci“ se řídí systémovým časem. Image `python:3.11-slim` běží v UTC. Pokud chcete půlnoc podle českého času, přidejte do `environment` proměnnou `TZ=Europe/Prague`.

### Bez Dockeru

```bash
./run.sh
```

Skript `run.sh` vytvoří virtuální prostředí `venv/`, nainstaluje závislosti, načte `.env`, zkontroluje, že je nastavený `POSTGREST_API_KEY`, a spustí `fetch_15min_data.py`.

Případně ručně:

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
export POSTGREST_API_KEY=your_api_key_here
export POSTGREST_URL=http://localhost:3000
python3 fetch_15min_data.py
```

## Formát dat

Na `POST {POSTGREST_URL}/rpc/insert_spot_price` se posílá:

```json
{
  "p_country_id": "0",
  "p_prices_for_date": "2025-11-02",
  "p_data_prices": {
    "exchange_rate": 24.35,
    "dates": {
      "00:00": { "price_eur_mwh": 98.5,  "price_czk_mwh": 2398.48 },
      "00:15": { "price_eur_mwh": 95.12, "price_czk_mwh": 2316.17 },
      "...": {},
      "23:45": { "price_eur_mwh": 87.3,  "price_czk_mwh": 2125.76 }
    }
  }
}
```

| Pole                | Popis                                                          |
|---------------------|----------------------------------------------------------------|
| `p_country_id`      | ID země, ve skriptu pevně nastavené na `"0"`                   |
| `p_prices_for_date` | Datum, ke kterému ceny patří (`YYYY-MM-DD`), z titulku grafu OTE |
| `exchange_rate`     | Kurz CZK za 1 EUR podle ČNB                                    |
| `dates`             | Ceny pro každou 15min periodu; CZK se zaokrouhlují na 2 desetinná místa |

Hlavičky požadavku: `Content-Type: application/json` a `x-api-key: <POSTGREST_API_KEY>`.

## Struktura projektu

```
.
├── fetch_15min_data.py   # hlavní skript (stažení, převod, odeslání, plánování)
├── requirements.txt      # Python závislosti (requests)
├── Dockerfile            # image založený na python:3.11-slim
├── docker-compose.yml    # služba spot_container
├── run.sh                # spuštění bez Dockeru
└── LICENSE               # GNU GPL v3
```

## Licence

Projekt je pod licencí [GNU General Public License v3.0](LICENSE).
