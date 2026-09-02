"""Holdings verisinin doğruluğunu ve tutarlılığını denetler.

Her fon için:
  1. Ağırlık toplamı ~%100 (normalize sonrası)
  2. shares × kapanış fiyatı ≈ market_value (market_value olan fonlarda)
  3. ticker → yfinance şirket adı çapraz kontrolü (isim örtüşmesi)
  4. yfinance'te fiyatı çekilemeyen (delisted/yanlış) ticker oranı

Kullanım: python3 dogrula.py [--hizli]   (--hizli: isim çapraz kontrolünü atla)
"""

import re
import sys
import warnings

warnings.filterwarnings("ignore")

import pandas as pd

from parsers import (parse_vaneck, parse_ishares, parse_spdr,
                     parse_invesco, parse_tema, parse_globalx, parse_roundhill)

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
]


def _norm(s):
    s = re.sub(r"[^a-z ]", " ", str(s).lower())
    at = {"inc", "corp", "corporation", "co", "ltd", "plc", "nv", "sa", "ag",
          "the", "class", "a", "b", "c", "holdings", "holding", "group",
          "technologies", "technology", "tech", "systems", "adr", "limited",
          "company", "sp", "spon", "com", "de", "cl"}
    return {w for w in s.split() if w and w not in at}


def dogrula(isim_kontrol=True, log=print):
    import yfinance as yf

    log(f"{'fon':5} {'hisse':>6} {'ağırlık':>8} {'mv tutarlı':>11} "
        f"{'fiyatsız':>9} {'isim şüpheli':>13}")
    sorun = 0

    for fon, parser, yol in FONLAR:
        try:
            d = parser(yol, fon)
        except Exception as e:
            log(f"{fon:5} PARSE HATASI: {type(e).__name__}: {e}")
            sorun += 1
            continue

        agirlik = d["weight"].sum()
        agirlik_ok = abs(agirlik - 100) < 0.5

        # market_value tutarlılığı: shares × (fonun KENDİ tarihindeki kapanış)
        # ≈ market_value. Yalnızca ABD-listeli tickerlar; yabancı borsalarda
        # yfinance fiyatı yerel para biriminde, market_value USD (FX farkı).
        mv = "—"
        abd = d[~d["ticker"].str.contains(r"\.\w+$", regex=True, na=False)]
        if abd["market_value"].notna().all() and len(abd):
            tarih = pd.Timestamp(d["date"].iloc[0])
            px = yf.download(list(abd["ticker"]),
                             start=tarih - pd.Timedelta(days=5),
                             end=tarih + pd.Timedelta(days=1),
                             auto_adjust=False, progress=False)["Close"]
            son = px.ffill().iloc[-1] if len(px) else pd.Series(dtype=float)
            ima = abd.set_index("ticker")["shares"] * son.reindex(abd["ticker"])
            oran = (ima / abd.set_index("ticker")["market_value"]).dropna()
            sapan = int(((oran - 1).abs() > 0.03).sum())
            yab = len(d) - len(abd)
            ek = f" (+{yab} yabancı)" if yab else ""
            mv = f"✓{ek}" if sapan == 0 else f"{sapan}/{len(oran)} sapan{ek}"

        # fiyatsız ticker
        px2 = yf.download(list(d["ticker"]), start="2026-08-20",
                          end="2026-09-02", auto_adjust=True,
                          progress=False)["Close"]
        bos = [t for t in d["ticker"]
               if t not in px2.columns or px2[t].isna().all()]
        fiyatsiz_a = d[d["ticker"].isin(bos)]["weight"].sum()
        fiyatsiz = "✓" if not bos else f"{len(bos)} (%{fiyatsiz_a:.1f})"

        # isim çapraz kontrol
        supheli = "—"
        if isim_kontrol:
            s = 0
            for t, ad in zip(d["ticker"], d["name"]):
                try:
                    yad = (yf.Ticker(t).info.get("longName")
                           or yf.Ticker(t).info.get("shortName") or "")
                except Exception:
                    yad = ""
                if yad and not (_norm(ad) & _norm(yad)):
                    s += 1
            supheli = "✓" if s == 0 else str(s)

        if not agirlik_ok or "sapan" in str(mv) or bos:
            sorun += 1
        log(f"{fon:5} {len(d):>6} {agirlik:>7.2f}% {mv:>11} "
            f"{fiyatsiz:>9} {str(supheli):>13}")

    log(f"\n{'⚠ ' + str(sorun) + ' fonda dikkat' if sorun else '✓ tüm fonlar temiz'}")
    return sorun


if __name__ == "__main__":
    dogrula(isim_kontrol="--hizli" not in sys.argv)
