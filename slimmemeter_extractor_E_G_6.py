#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Sun Mar  1 22:07:06 2026

@author: stef
"""

"""
SlimmeMeterPortal - Elektriciteit + Gas + Temperatuur extractor
===============================================================
Haalt verbruiks-, terugleverings-, gas- en temperatuurdata op via
automatisch inloggen, voor één of meerdere dagen tegelijk.

Gebruik:
    # Gisteren (standaard)
    python slimmemeter_extractor.py

    # Specifieke datum
    python slimmemeter_extractor.py --van 2026-02-01

    # Datumbereik
    python slimmemeter_extractor.py --van 2026-02-01 --tot 2026-02-17

    # Lokaal HTML-bestand (zonder inloggen)
    python slimmemeter_extractor.py --html pagina.html

    # Alleen elektriciteit (geen gas/temperatuur)
    python slimmemeter_extractor.py --geen-gas

Output: één CSV-bestand (verbruik.csv):
    tijd | teruglevering_laag | teruglevering_normaal |
    verbruik_laag | verbruik_normaal | gas_m3 | temperatuur_c

    Elektriciteit per kwartier; gas/temperatuur alleen op hele uren (rest leeg).

Vereisten:
    pip install requests beautifulsoup4 pandas
"""

import argparse
import json
import sys
import time
from   datetime   import date, datetime, timedelta

import pandas     as pd
import requests
from   bs4        import BeautifulSoup

# ============================================================
# CONFIGURATIE — vul hier je inloggegevens in
# ============================================================
EMAIL      = "jouw@email.nl"
WACHTWOORD = "jouwwachtwoord"
# ============================================================

BASE_URL   = "https://app.slimmemeterportal.nl"
LOGIN_URL  = f"{BASE_URL}/login"
POST_URL   = f"{BASE_URL}/user_session"
DATA_URL   = f"{BASE_URL}/verbruik"
CHART_URL  = f"{BASE_URL}/cust/consumption/chart.turbo_stream"

# ── Kolommen elektriciteit ────────────────────────────────────
KOLOM_VOLGORDE_ELEK = [
    "tijd",
    "teruglevering_laag",
    "teruglevering_normaal",
    "verbruik_laag",
    "verbruik_normaal",
]

LABEL_MAP_ELEK = {
    # Dubbel tarief
    "verbruik laagtarief":         "verbruik_laag",
    "verbruik normaaltarief":      "verbruik_normaal",
    "teruglevering laagtarief":    "teruglevering_laag",
    "teruglevering normaaltarief": "teruglevering_normaal",
    # Enkeltarief (single rate)
    "verbruik totaal":             "verbruik_normaal",
    "teruglevering totaal":        "teruglevering_normaal",
}

# ── Kolommen gas (intern) & gecombineerd ─────────────────────
KOLOM_VOLGORDE_GAS = ["tijd", "gas_m3", "temperatuur_c"]
KOLOM_VOLGORDE_GECOMBINEERD = [
    "tijd",
    "teruglevering_laag",
    "teruglevering_normaal",
    "teruglevering",
    "verbruik_laag",
    "verbruik_normaal",
    "verbruik",
    "gas_m3",
    "temperatuur_c",
]


# ── Inloggen ──────────────────────────────────────────────────

def maak_sessie() -> requests.Session:
    sessie = requests.Session()
    sessie.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                      "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Accept":          "text/html,application/xhtml+xml,*/*;q=0.8",
        "Accept-Language": "nl-NL,nl;q=0.9,en;q=0.8",
    })
    return sessie


def login(sessie: requests.Session) -> bool:
    """Log in via /login → POST /user_session. Geeft True terug bij succes."""
    print("Inloggen op SlimmeMeterPortal...", end=" ", flush=True)

    resp = sessie.get(LOGIN_URL, timeout=15)
    soup = BeautifulSoup(resp.text, "html.parser")

    token = ""
    inp = soup.find("input", {"name": "authenticity_token"})
    if inp:
        token = inp.get("value", "")

    payload = {
        "authenticity_token":     token,
        "user_session[email]":    EMAIL,
        "user_session[password]": WACHTWOORD,
        "button": "",
    }

    resp = sessie.post(POST_URL, data=payload, allow_redirects=True, timeout=15)

    geslaagd = "login" not in resp.url and resp.status_code < 400
    print("✓ gelukt" if geslaagd else "✗ mislukt")
    if not geslaagd:
        print(f"  URL na login: {resp.url}")
        print("  Controleer EMAIL en WACHTWOORD bovenin het script.")
    return geslaagd


# ── Contract ID & data ophalen ────────────────────────────────

def haal_contract_id(sessie: requests.Session) -> str | None:
    """Haal het contract_id op van de verbruikspagina."""
    resp = sessie.get(DATA_URL, timeout=15)
    soup = BeautifulSoup(resp.text, "html.parser")
    inp = soup.find("input", {"name": "contract_id"})
    return inp.get("value") if inp else None


def datum_naar_unix(d: date) -> int:
    """Zet datum om naar Unix-timestamp van middernacht Amsterdam-tijd."""
    import zoneinfo
    tz = zoneinfo.ZoneInfo("Europe/Amsterdam")
    dt = datetime(d.year, d.month, d.day, 0, 0, 0, tzinfo=tz)
    return int(dt.timestamp())


def haal_dag_html(sessie: requests.Session, contract_id: str,
                  dag: date, commodity: str = "power") -> str:
    """Haal de grafiek-HTML op voor één dag en één commodity (power of gas)."""
    params = {
        "commodity":      commodity,
        "contract_id":    contract_id,
        "contracts[]":    contract_id,
        "datatype":       "consumption",
        "meter_type":     "point_of_connection",
        "range":          "86400",
        "timeslot_start": datum_naar_unix(dag),
    }
    resp = sessie.get(CHART_URL, params=params, timeout=15)
    resp.raise_for_status()
    return resp.text


def haal_dag_html_uit_bestand(pad: str) -> str:
    from pathlib import Path
    return Path(pad).read_text(encoding="utf-8", errors="replace")


# ── Data verwerken: elektriciteit ────────────────────────────

def extraheer_series(html: str) -> list[dict]:
    """Haal de Highcharts series op uit data-chart-series-value."""
    soup = BeautifulSoup(html, "html.parser")
    grafiek = soup.find(attrs={"data-chart-series-value": True})
    if not grafiek:
        raise ValueError("Geen grafiekdata gevonden in de HTML.")
    return json.loads(grafiek["data-chart-series-value"])


def extraheer_chart_data(html: str) -> dict:
    """Haal het volledige data-chart-data-value object op (bevat weather_series)."""
    soup = BeautifulSoup(html, "html.parser")
    grafiek = soup.find(attrs={"data-chart-data-value": True})
    if not grafiek:
        return {}
    return json.loads(grafiek["data-chart-data-value"])


def series_naar_elek_df(series: list[dict]) -> pd.DataFrame:
    """
    Groepeert de 4 elektriciteitseries tot een breed DataFrame:
      tijd | teruglevering_laag | teruglevering_normaal |
      verbruik_laag | verbruik_normaal
    Teruglevering (negatief in bron) wordt positief gemaakt.
    """
    tijdstip_data: dict[str, dict[str, float]] = {}

    for serie in series:
        label     = serie.get("label", "")
        kolomnaam = LABEL_MAP_ELEK.get(label)
        if kolomnaam is None:
            continue

        for punt in serie.get("data", []):
            t = punt["x"]
            v = punt["y"] or 0.0
            if t not in tijdstip_data:
                tijdstip_data[t] = {}
            tijdstip_data[t][kolomnaam] = v

    if not tijdstip_data:
        return pd.DataFrame(columns=KOLOM_VOLGORDE_ELEK)

    df = pd.DataFrame.from_dict(tijdstip_data, orient="index")
    df.index = pd.to_datetime(df.index, utc=True).tz_convert("Europe/Amsterdam")
    df.index.name = "tijd"
    df = df.reset_index()

    for kolom in KOLOM_VOLGORDE_ELEK[1:]:
        if kolom not in df.columns:
            df[kolom] = 0.0

    df = df[KOLOM_VOLGORDE_ELEK].sort_values("tijd").reset_index(drop=True)

    for kolom in ["teruglevering_laag", "teruglevering_normaal"]:
        df[kolom] = df[kolom].abs()

    return df


# ── Data verwerken: gas + temperatuur ────────────────────────

def series_naar_gas_df(series: list[dict], chart_data: dict) -> pd.DataFrame:
    """
    Haalt gasverbruik (m³, per uur) en buitentemperatuur (°C, per uur) op.

    Gasverbruik zit in series met label 'verbruik totaal'.
    Temperatuur zit in chart_data['weather_series']['data'].
    """
    tijdstip_data: dict[str, dict] = {}

    # Gas
    for serie in series:
        if serie.get("label", "") != "verbruik totaal":
            continue
        for punt in serie.get("data", []):
            t = punt["x"]
            v = punt["y"] if punt["y"] is not None else 0.0
            if t not in tijdstip_data:
                tijdstip_data[t] = {}
            tijdstip_data[t]["gas_m3"] = v

    # Temperatuur uit weather_series in chart_data
    weather = chart_data.get("weather_series")
    if weather and isinstance(weather, dict):
        for punt in weather.get("data", []):
            t = punt["x"]
            v = punt["y"] if punt["y"] is not None else None
            if t not in tijdstip_data:
                tijdstip_data[t] = {}
            tijdstip_data[t]["temperatuur_c"] = v

    if not tijdstip_data:
        return pd.DataFrame(columns=KOLOM_VOLGORDE_GAS)

    df = pd.DataFrame.from_dict(tijdstip_data, orient="index")
    df.index = pd.to_datetime(df.index, utc=True).tz_convert("Europe/Amsterdam")
    df.index.name = "tijd"
    df = df.reset_index()

    for kolom in KOLOM_VOLGORDE_GAS[1:]:
        if kolom not in df.columns:
            df[kolom] = None

    df = df[KOLOM_VOLGORDE_GAS].sort_values("tijd").reset_index(drop=True)
    return df


# ── Samenvatting ──────────────────────────────────────────────

def toon_samenvatting(elek_df: pd.DataFrame, gas_df: pd.DataFrame | None) -> None:
    print("\n=== Samenvatting per dag ===")

    if elek_df.empty:
        print("Geen elektriciteitsdata.")
    else:
        for dag, groep in elek_df.groupby(elek_df["tijd"].dt.date):
            print(f"\n  {dag} — Elektriciteit:")
            for kolom in KOLOM_VOLGORDE_ELEK[1:]:
                print(f"    {kolom:<30} {groep[kolom].sum():>8.3f} kWh")

    if gas_df is not None and not gas_df.empty:
        for dag, groep in gas_df.groupby(gas_df["tijd"].dt.date):
            gas_totaal = groep["gas_m3"].sum()
            gem_temp   = groep["temperatuur_c"].mean()
            print(f"\n  {dag} — Gas:")
            print(f"    {'gas_m3':<30} {gas_totaal:>8.3f} m³")
            if pd.notna(gem_temp):
                print(f"    {'gem. temperatuur':<30} {gem_temp:>8.1f} °C")

    print()


# ── Hoofdprogramma ────────────────────────────────────────────

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="SlimmeMeterPortal data extractor (elektriciteit + gas + temperatuur)"
    )
    parser.add_argument("--van",      metavar="JJJJ-MM-DD", help="Begindatum (standaard: gisteren)")
    parser.add_argument("--tot",      metavar="JJJJ-MM-DD", help="Einddatum inclusief")
    parser.add_argument("--uitvoer",  metavar="bestand.csv", default="verbruik.csv",
                        help="Uitvoerbestand (standaard: verbruik.csv)")
    parser.add_argument("--html",     metavar="bestand.html",
                        help="Lokaal HTML-bestand verwerken (elektriciteit)")
    parser.add_argument("--html-gas", metavar="bestand.html",
                        help="Lokaal HTML-bestand verwerken (gas)")
    parser.add_argument("--geen-gas", action="store_true",
                        help="Sla gasdata over (alleen elektriciteit ophalen)")
    return parser.parse_args()


# **************************************************************************
# **************************************************************************
def main() -> None:
    args = parse_args()
    elek_dfs: list[pd.DataFrame] = []
    gas_dfs:  list[pd.DataFrame] = []

    # ── Modus 1: lokale HTML-bestanden ───────────────────────
    if args.html or args.html_gas:
        if args.html:
            print(f"Elektriciteit uit bestand: {args.html}")
            html   = haal_dag_html_uit_bestand(args.html)
            series = extraheer_series(html)
            elek_dfs.append(series_naar_elek_df(series))

        if args.html_gas and not args.geen_gas:
            print(f"Gas uit bestand: {args.html_gas}")
            html       = haal_dag_html_uit_bestand(args.html_gas)
            series     = extraheer_series(html)
            chart_data = extraheer_chart_data(html)
            gas_dfs.append(series_naar_gas_df(series, chart_data))

    # ── Modus 2: automatisch inloggen ─────────────────────────
    else:
        gisteren = date.today() - timedelta(days=1)
        van = date.fromisoformat(args.van) if args.van else gisteren
        tot = date.fromisoformat(args.tot) if args.tot else van

        if van > tot:
            print("Fout: --van mag niet later zijn dan --tot")
            sys.exit(1)

        dagen = [van + timedelta(days=i) for i in range((tot - van).days + 1)]
        print(f"Periode: {van} t/m {tot}  ({len(dagen)} dag{'en' if len(dagen) != 1 else ''})")

        sessie = maak_sessie()
        if not login(sessie):
            sys.exit(1)

        contract_id = haal_contract_id(sessie)
        if not contract_id:
            print("Kon contract_id niet vinden. Mogelijk is inloggen mislukt.")
            sys.exit(1)
        print(f"Contract ID: {contract_id}\n")

        for dag in dagen:
            # — Elektriciteit —
            print(f"  {dag} [elektriciteit]...", end=" ", flush=True)
            try:
                html   = haal_dag_html(sessie, contract_id, dag, commodity="power")
                series = extraheer_series(html)
                df     = series_naar_elek_df(series)
                if df.empty:
                    print("geen data")
                else:
                    elek_dfs.append(df)
                    print(f"{len(df)} meetpunten")
            except Exception as e:
                print(f"fout: {e}")

            time.sleep(0.4)

            # — Gas —
            if not args.geen_gas:
                print(f"  {dag} [gas]...", end=" ", flush=True)
                try:
                    html       = haal_dag_html(sessie, contract_id, dag, commodity="gas")
                    series     = extraheer_series(html)
                    chart_data = extraheer_chart_data(html)
                    df_gas     = series_naar_gas_df(series, chart_data)
                    if df_gas.empty:
                        print("geen data")
                    else:
                        gas_dfs.append(df_gas)
                        print(f"{len(df_gas)} meetpunten")
                except Exception as e:
                    print(f"fout: {e}")

                if dag != dagen[-1]:
                    time.sleep(0.4)

    # ── Resultaten samenvoegen en opslaan ────────────────────
    elek_resultaat = pd.DataFrame()
    gas_resultaat  = None

    if elek_dfs:
        elek_resultaat = (
            pd.concat(elek_dfs, ignore_index=True)
            .sort_values("tijd")
            .reset_index(drop=True)
        )
    else:
        print("\nGeen elektriciteitsdata gevonden.")

    if gas_dfs:
        gas_resultaat = (
            pd.concat(gas_dfs, ignore_index=True)
            .sort_values("tijd")
            .reset_index(drop=True)
        )

    toon_samenvatting(elek_resultaat, gas_resultaat)

    if elek_resultaat.empty and (gas_resultaat is None or gas_resultaat.empty):
        print("Geen data gevonden.")
        sys.exit(1)

    # Combineer: elektriciteit (per kwartier) + gas/temp (per uur)
    # Gas-tijdstipppen worden afgerond op het uur; elektriciteit-tijdstippen ook
    # zodat we op "heel uur" kunnen joinen.
    if not elek_resultaat.empty and gas_resultaat is not None and not gas_resultaat.empty:
        # Voeg een join-sleutel toe: elektriciteitsrij afgeronden naar uur
        elek_resultaat["_uur"] = elek_resultaat["tijd"].dt.floor("h")
        gas_sleutel = gas_resultaat.copy()
        gas_sleutel["_uur"] = gas_sleutel["tijd"].dt.floor("h")
        gas_sleutel = gas_sleutel.drop(columns=["tijd"])

        gecombineerd = elek_resultaat.merge(gas_sleutel, on="_uur", how="left")
        gecombineerd = gecombineerd.drop(columns=["_uur"])
    elif not elek_resultaat.empty:
        gecombineerd = elek_resultaat.copy()
        gecombineerd["gas_m3"]       = None
        gecombineerd["temperatuur_c"] = None
    else:
        # Alleen gas (ongebruikelijk maar afgevangen)
        gecombineerd = gas_resultaat.copy()

    # Zorg dat alle kolommen aanwezig zijn
    for kolom in KOLOM_VOLGORDE_GECOMBINEERD:
        if kolom not in gecombineerd.columns:
            gecombineerd[kolom] = None

    # Totaalkolommen
    gecombineerd["teruglevering"] = gecombineerd["teruglevering_laag"].fillna(0) + gecombineerd["teruglevering_normaal"].fillna(0)
    gecombineerd["verbruik"]      = gecombineerd["verbruik_laag"].fillna(0) + gecombineerd["verbruik_normaal"].fillna(0)

    # Gas van liters naar m³
    gecombineerd["gas_m3"] = gecombineerd["gas_m3"]

    gecombineerd = (
        gecombineerd[KOLOM_VOLGORDE_GECOMBINEERD]
        .sort_values("tijd")
        .reset_index(drop=True)
    )

    gecombineerd.to_csv(args.uitvoer, index=False, sep=";")
    print(f"✓ {len(gecombineerd)} meetpunten → '{args.uitvoer}'")
    print(gecombineerd.head(8).to_string(index=False))
    print()

# **************************************************************************
# ── Hoofdprogramma ────────────────────────────────────────────
# **************************************************************************
if __name__ == "__main__":
    main()


"""
Libre Office: Inlezen, maak alle kolommen (behalve de eerste) type "TEXT"


$ mamba env list
$ mamba activate test_env

(test_env) stef@fedora:~/Nextcloud/Data/Data_Python_25/SlimmeMeterPortal$ py slimmemeter_extractor_E_G_6.py --van 2026-02-01 --tot 2026-02-28 --uitvoer SW_2026_2.csv^C
(test_env) stef@fedora:~/Nextcloud/Data/Data_Python_25/SlimmeMeterPortal$ 
$ py slimmemeter_extractor_E_G_6.py --van 2026-02-01 --tot 2026-02-28 --uitvoer SW_2026_2.csv

(test_env) stef@fedora:~/Nextcloud/Data/Data_Python_25/SlimmeMeterPortal$ 
  py slimmemeter_extractor_E_G_6.py --help
usage: slimmemeter_extractor_E_G_6.py [-h] [--van JJJJ-MM-DD] [--tot JJJJ-MM-DD] [--uitvoer bestand.csv] [--html bestand.html]
                                      [--html-gas bestand.html] [--geen-gas]

SlimmeMeterPortal data extractor (elektriciteit + gas + temperatuur)

options:
  -h, --help            show this help message and exit
  --van JJJJ-MM-DD      Begindatum (standaard: gisteren)
  --tot JJJJ-MM-DD      Einddatum inclusief
  --uitvoer bestand.csv
                        Uitvoerbestand (standaard: verbruik.csv)
  --html bestand.html   Lokaal HTML-bestand verwerken (elektriciteit)
  --html-gas bestand.html
                        Lokaal HTML-bestand verwerken (gas)
  --geen-gas            Sla gasdata over (alleen elektriciteit ophalen)

"""    
    
    
    