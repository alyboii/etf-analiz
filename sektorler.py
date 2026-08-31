"""Ticker -> Türkçe sektör haritası.

Tüm fonlardaki benzersiz hisseler için sektör belirler ve
data/sektorler.parquet'e yazar. Kaynak: öncelikle yfinance `industry`
(ABD + yabancı borsalar için temiz ve granüler), olmazsa holdings
dosyasındaki sektör, o da yoksa "Diğer".

Uygulama bu parquet'i okur; ağ çağrısı yalnızca bu dosya üretilirken yapılır.
Yeni fon/ticker eklenince yeniden çalıştır: python3 sektorler.py
"""

import time
import warnings
from pathlib import Path

import pandas as pd
import yfinance as yf

warnings.filterwarnings("ignore")

from parsers import (parse_vaneck, parse_ishares, parse_spdr,
                     parse_invesco, parse_tema, parse_globalx,
                     parse_roundhill)

CIKTI = Path("data/sektorler.parquet")

# (fon, parser, yol) — app.py'daki FONLAR ile aynı kaynaklar
FONLAR = [
    ("SMH",  parse_vaneck,  "data/raw/SMH_asof_20260827.xlsx"),
    ("SOXX", parse_ishares, "data/raw/SOXX_holdings.csv"),
    ("XSD",  parse_spdr,    "data/raw/holdings-daily-us-en-xsd.xlsx"),
    ("SMHX", parse_vaneck,  "data/raw/SMHX_asof_20260828.xlsx"),
    ("SOXQ", parse_invesco, "data/raw/invesco_phlx_semiconductor_etf-"
                            "Complete_Holdings.csv"),
    ("PSI",  parse_invesco, "data/raw/invesco_semiconductors_etf-"
                            "Complete_Holdings.csv"),
    ("ROKT", parse_spdr,    "data/raw/holdings-daily-us-en-rokt.xlsx"),
    ("NASA", parse_tema,    "data/raw/NASA-holdings-08282026.csv"),
    ("IGV",  parse_ishares, "data/raw/IGV_holdings.csv"),
    ("AIQ",  parse_globalx, "data/raw/aiq_full-holdings_20260828.csv"),
    ("CHAT", parse_roundhill, "data/raw/CHAT_ETF_Holdings_08-30-2026.csv"),
    # UFO dosyası gelince buraya eklenir
]


def _kova(industry, sektor):
    """yfinance industry (ya da kaynak sektör) -> Türkçe kova."""
    m = f"{industry or ''} {sektor or ''}".lower()
    if "semiconductor" in m:
        return "Yarı İletken"
    if "aerospace" in m or "defense" in m:
        return "Havacılık & Savunma"
    if "oil" in m or "gas" in m or "energy" in m:
        return "Enerji"
    if "software" in m or "internet" in m:
        return "Yazılım"
    if "communication" in m or "telecom" in m:
        return "İletişim"
    if ("hardware" in m or "electronic" in m or "computer" in m
            or "instruments" in m):
        return "Donanım"
    if "industrial" in m or "machinery" in m or "manufactur" in m:
        return "Sanayi"
    if "financ" in m or "bank" in m or "capital markets" in m:
        return "Finans"
    if m.strip():
        return "Diğer Teknoloji"
    return "Diğer"


def topla(log=print):
    # ticker -> holdings'teki sektör (varsa)
    ticker_sektor = {}
    for fon, parser, yol in FONLAR:
        d = parser(yol, fon)
        for t, s in zip(d["ticker"], d["sector"]):
            if t not in ticker_sektor or pd.isna(ticker_sektor[t]):
                ticker_sektor[t] = s

    tickerlar = sorted(ticker_sektor)
    log(f"{len(tickerlar)} benzersiz ticker için sektör çekiliyor...")

    rows = []
    for i, t in enumerate(tickerlar, 1):
        industry = None
        try:
            info = yf.Ticker(t).info
            industry = info.get("industry")
        except Exception:
            pass
        kaynak_sektor = ticker_sektor.get(t)
        rows.append({
            "ticker": t,
            "industry": industry,
            "kaynak_sektor": kaynak_sektor,
            "sektor": _kova(industry, kaynak_sektor),
        })
        if i % 25 == 0:
            log(f"  {i}/{len(tickerlar)}")
        time.sleep(0.15)

    df = pd.DataFrame(rows)
    CIKTI.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(CIKTI, index=False)
    log(f"\nyazıldı: {CIKTI} ({len(df)} ticker)")
    log("\nsektör dağılımı:")
    log(df["sektor"].value_counts().to_string())
    return df


def yukle():
    """Ticker -> Türkçe sektör sözlüğü. Parquet yoksa boş döner."""
    if not CIKTI.exists():
        return {}
    df = pd.read_parquet(CIKTI)
    return dict(zip(df["ticker"], df["sektor"]))


if __name__ == "__main__":
    topla()
