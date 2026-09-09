"""Ticker -> ülke haritası (şirketin menşe ülkesi).

Tüm fonlardaki benzersiz hisseler için yfinance `country` alanını çeker ve
data/ulkeler.parquet'e yazar. yfinance şirketin GERÇEK menşe ülkesini verir:
ör. TSM (ABD'de işlem gören ADR) -> Taiwan, ARM -> United Kingdom. Böylece
"fonun ne kadarı ABD, ne kadarı yabancı" sorusu doğru cevaplanır.

Uygulama bu parquet'i okur; ağ çağrısı yalnızca bu dosya üretilirken yapılır.
Yeni fon/ticker eklenince yeniden çalıştır: python3 ulkeler.py
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

CIKTI = Path("data/ulkeler.parquet")

# app.py'daki FONLAR ile aynı kaynaklar
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
    ("XSW",  parse_spdr,    "data/raw/holdings-daily-us-en-xsw.xlsx"),
    ("AIQ",  parse_globalx, "data/raw/aiq_full-holdings_20260828.csv"),
    ("CHAT", parse_roundhill, "data/raw/CHAT_ETF_Holdings_08-30-2026.csv"),
]

# yfinance country (İngilizce) -> (Türkçe ad, bayrak emoji)
ULKE_TR = {
    "United States": ("ABD", "🇺🇸"),
    "Taiwan": ("Tayvan", "🇹🇼"),
    "China": ("Çin", "🇨🇳"),
    "South Korea": ("Güney Kore", "🇰🇷"),
    "Korea, Republic of": ("Güney Kore", "🇰🇷"),
    "Japan": ("Japonya", "🇯🇵"),
    "Netherlands": ("Hollanda", "🇳🇱"),
    "Germany": ("Almanya", "🇩🇪"),
    "United Kingdom": ("Birleşik Krallık", "🇬🇧"),
    "France": ("Fransa", "🇫🇷"),
    "Switzerland": ("İsviçre", "🇨🇭"),
    "Israel": ("İsrail", "🇮🇱"),
    "Canada": ("Kanada", "🇨🇦"),
    "Ireland": ("İrlanda", "🇮🇪"),
    "Italy": ("İtalya", "🇮🇹"),
    "Sweden": ("İsveç", "🇸🇪"),
    "Finland": ("Finlandiya", "🇫🇮"),
    "Singapore": ("Singapur", "🇸🇬"),
    "Hong Kong": ("Hong Kong", "🇭🇰"),
    "Australia": ("Avustralya", "🇦🇺"),
    "Belgium": ("Belçika", "🇧🇪"),
    "Norway": ("Norveç", "🇳🇴"),
    "Denmark": ("Danimarka", "🇩🇰"),
    "Spain": ("İspanya", "🇪🇸"),
    "Austria": ("Avusturya", "🇦🇹"),
    "India": ("Hindistan", "🇮🇳"),
    "Luxembourg": ("Lüksemburg", "🇱🇺"),
}


def _tr(country):
    if not country or pd.isna(country):
        return "Bilinmiyor", "🏳️"
    return ULKE_TR.get(str(country).strip(), (str(country).strip(), "🏴"))


def topla(log=print):
    tickerlar = set()
    for fon, parser, yol in FONLAR:
        d = parser(yol, fon)
        tickerlar.update(d["ticker"])
    tickerlar = sorted(tickerlar)
    log(f"{len(tickerlar)} benzersiz ticker için ülke çekiliyor...")

    rows = []
    for i, t in enumerate(tickerlar, 1):
        country = None
        try:
            country = yf.Ticker(t).info.get("country")
        except Exception:
            pass
        tr, bayrak = _tr(country)
        rows.append({
            "ticker": t,
            "country": country,
            "ulke": tr,
            "bayrak": bayrak,
        })
        if i % 25 == 0:
            log(f"  {i}/{len(tickerlar)}")
        time.sleep(0.15)

    df = pd.DataFrame(rows)
    CIKTI.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(CIKTI, index=False)
    log(f"\nyazıldı: {CIKTI} ({len(df)} ticker)")
    log("\nülke dağılımı (ticker sayısı):")
    log(df["ulke"].value_counts().to_string())
    return df


def yukle():
    """Ticker -> (ülke_tr, bayrak) sözlüğü. Parquet yoksa boş döner."""
    if not CIKTI.exists():
        return {}
    df = pd.read_parquet(CIKTI)
    return {t: (u, b) for t, u, b in zip(df["ticker"], df["ulke"], df["bayrak"])}


if __name__ == "__main__":
    topla()
