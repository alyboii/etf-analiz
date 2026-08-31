
import re

import pandas as pd


def parse_ishares(dosya_yolu, fon_adi):
    # Tarih: dosyanın 2. satırında → Fund Holdings as of,"Aug 27, 2026"
    with open(dosya_yolu) as f:
        satirlar = f.readlines()
    tarih_str = satirlar[1].split(",", 1)[1].strip().strip('"')
    tarih = pd.to_datetime(tarih_str)


    # Oku: 9 satır metadata + boş satır
    df = pd.read_csv(dosya_yolu, skiprows=9)

    # Sadece hisseler
    df = df[df["Asset Class"] == "Equity"].copy()

    # Weight ZATEN float, dokunma
    df["weight"] = df["Weight (%)"].astype(float)

    # Bunlar metin, virgülleri temizle
    df["market_value"] = df["Market Value"].str.replace(",", "").astype(float)
    df["shares"] = df["Quantity"].str.replace(",", "").astype(float).astype(int)

    # Normalize
    df["weight"] = df["weight"] / df["weight"].sum() * 100

    # Standart kolonlar
    df = df[["Ticker", "Name", "shares", "market_value", "weight",
             "Sector", "Location"]].copy()
    df.columns = ["ticker", "name", "shares", "market_value", "weight",
                  "sector", "location"]

    df["figi"] = None          # iShares FIGI vermiyor
    df["fund"] = fon_adi
    df["date"] = tarih

    return df.reset_index(drop=True)


def hisse_sinifi_ticker(t):
    """SSGA hisse sınıfını nokta ile yazıyor, yfinance tire istiyor.

    "MOG.A" -> "MOG-A". Sadece noktadan sonra tek harf varsa uygulanır;
    yabancı borsa sonekleri (".L", ".TO") bu parser'da geçmiyor.
    """
    t = str(t).strip()
    parca = t.split(".")
    if len(parca) == 2 and len(parca[1]) == 1 and parca[1].isalpha():
        return f"{parca[0]}-{parca[1]}"
    return t


def parse_spdr(dosya_yolu, fon_adi):
    # Tarih: 3. satır, 2. kolon → "As of 27-Aug-2026"
    ust = pd.read_excel(dosya_yolu, header=None, nrows=3)
    tarih_str = str(ust.iloc[2, 1]).replace("As of ", "").strip()
    tarih = pd.to_datetime(tarih_str, format="%d-%b-%Y")

    # Oku: başlık 5. satırda
    df = pd.read_excel(dosya_yolu, skiprows=4)

    # Yasal metin satırlarında ticker boş, nakit satırlarında "-"
    df = df[df["Ticker"].notna() & (df["Ticker"] != "-")].copy()

    # Weight ve Shares Held zaten sayı
    df["weight"] = df["Weight"].astype(float)
    df["shares"] = df["Shares Held"].astype(float).astype(int)

    # Normalize
    df["weight"] = df["weight"] / df["weight"].sum() * 100

    # Standart kolonlar
    df = df[["Ticker", "Name", "shares", "weight", "Identifier"]].copy()
    df.columns = ["ticker", "name", "shares", "weight", "cusip"]

    df["ticker"] = df["ticker"].map(hisse_sinifi_ticker)

    df["market_value"] = None   # SPDR piyasa değeri vermiyor
    df["sector"] = None         # dosyadaki Sector kolonu hep "-"
    df["location"] = None
    df["figi"] = None
    df["fund"] = fon_adi
    df["date"] = tarih

    return df.reset_index(drop=True)


def parse_vaneck(dosya_yolu, fon_adi):
    df = pd.read_excel(dosya_yolu, skiprows=2)

    # Tarih dosya adından: SMH_asof_20260827.xlsx
    tarih_str = dosya_yolu.split("asof_")[1].replace(".xlsx", "")
    tarih = pd.to_datetime(tarih_str, format="%Y%m%d")

    df = df[df["Asset Class"] == "Stock"].copy()

    df["weight"] = df["% of Net Assets"].str.replace("%", "").str.strip().astype(float)
    df["market_value"] = (
        df["Market Value (US$)"]
        .str.replace("$", "").str.replace(",", "").str.strip()
        .astype(float)
    )
    df["shares"] = df["Shares"].str.replace(",", "").astype(int)

    df["weight"] = df["weight"] / df["weight"].sum() * 100

    df = df[["Ticker", "Holding Name", "Identifier (FIGI)",
             "shares", "market_value", "weight"]].copy()
    df.columns = ["ticker", "name", "figi", "shares", "market_value", "weight"]

    df["cusip"] = None
    df["sector"] = None
    df["location"] = None
    df["fund"] = fon_adi
    df["date"] = tarih

    return df.reset_index(drop=True)



def parse_invesco(dosya_yolu, fon_adi):
    # Tarih dosyanın SON satırında yorum olarak: "# as of 2026-08-28"
    with open(dosya_yolu) as f:
        satirlar = [x.strip() for x in f if x.strip()]
    tarih_satiri = next(x for x in reversed(satirlar) if x.startswith("#"))
    tarih = pd.to_datetime(tarih_satiri.split("as of")[1].strip())

    # comment="#" son satırı atlar
    df = pd.read_csv(dosya_yolu, comment="#")

    # Sadece hisse; nakit/para piyasası/temettü satırları elenir
    HISSE = ["Common Stock", "American Depository Receipt",
             "American Depository Receipt - NY"]
    df = df[df["Class of shares"].isin(HISSE)].copy()

    # Hepsi metin: "13.95%", "1,898,979.00", "$413,122,881.45"
    df["weight"] = df["% TNA"].str.rstrip("%").astype(float)
    df["shares"] = (
        df["Share/ Par"].str.replace(",", "").astype(float).astype(int)
    )
    df["market_value"] = (
        df["Market value"]
        .str.replace("$", "").str.replace(",", "").str.strip()
        .astype(float)
    )

    # Normalize
    df["weight"] = df["weight"] / df["weight"].sum() * 100

    # Standart kolonlar
    df = df[["Ticker", "Company", "shares", "market_value", "weight",
             "CUSIP"]].copy()
    df.columns = ["ticker", "name", "shares", "market_value", "weight",
                  "cusip"]

    df["sector"] = None         # Invesco dosyasında sektör yok
    df["location"] = None
    df["figi"] = None
    df["fund"] = fon_adi
    df["date"] = tarih

    return df.reset_index(drop=True)


# Bloomberg borsa kodu -> yfinance son eki
BORSA_SONEK = {
    "TT": ".TW",   "LN": ".L",   "CN": ".TO",  "JP": ".T",   "GR": ".DE",
    "KS": ".KS",   "PW": ".WA",  "HK": ".HK",  "FP": ".PA",  "IM": ".MI",
    "SS": ".ST",   "AU": ".AX",  "SW": ".SW",  "NA": ".AS",  "SM": ".MC",
    "FH": ".HE",   "HB": ".BR",  "SP": ".SI",  "NO": ".OL",
    "C2": ".SZ",   "C1": ".SS",  "CG": ".SS",
}

# Döviz/nakit satırlarında görülen kodlar (hisse değil, elenmeli)
DOVIZ_KODLARI = {"CNY", "EUR", "KRW", "TWD", "USD", "JPY", "HKD", "GBP",
                 "CHF", "SGD", "CAD", "AUD", "SEK", "NOK", "DKK", "PLN"}

# Standart son ekin tutmadığı istisnalar (Tayvan OTC pazarı .TWO kullanıyor)
TICKER_ISTISNA = {
    "3491 TT": "3491.TWO",   # Universal Microwave Technology
    "3105 TT": "3105.TWO",   # WIN Semiconductors
}


def bloomberg_ticker(t):
    """Bloomberg sembolünü yfinance sembolüne çevirir.

    "3491 TT" -> "3491.TWO", "AIXA GR" -> "AIXA.DE", "700 HK" -> "0700.HK",
    "RKLB" -> "RKLB".
    """
    t = str(t).strip()
    if t in TICKER_ISTISNA:
        return TICKER_ISTISNA[t]
    parca = t.split()
    if len(parca) == 2 and parca[1] in BORSA_SONEK:
        kod, borsa = parca
        # Hong Kong sembolleri yfinance'te 4 haneye tamamlanır (700 -> 0700)
        if borsa == "HK" and kod.isdigit():
            kod = kod.zfill(4)
        return kod + BORSA_SONEK[borsa]
    return t


def parse_tema(dosya_yolu, fon_adi):
    df = pd.read_csv(dosya_yolu)

    tarih = pd.to_datetime(df["holdings_date"].iloc[0])

    # Nakit satırlarını at
    df = df[df["is_cash"] == 0].copy()

    # percent_of_nav oran olarak geliyor (0.1696 = %16.96)
    df["weight"] = df["percent_of_nav"].astype(float) * 100
    df["weight"] = df["weight"] / df["weight"].sum() * 100

    df["shares"] = df["shares"].astype(float)
    df["market_value"] = df["market_value"].astype(float)

    # Yabancı borsalar Bloomberg formatında; yfinance sembolüne çevir
    df["ticker"] = df["ticker"].map(bloomberg_ticker)

    df = df[["ticker", "proper_name", "shares", "market_value", "weight",
             "sector", "country", "cusip"]].copy()
    df.columns = ["ticker", "name", "shares", "market_value", "weight",
                  "sector", "location", "cusip"]

    df["figi"] = None
    df["fund"] = fon_adi
    df["date"] = tarih

    return df.reset_index(drop=True)


def parse_globalx(dosya_yolu, fon_adi):
    # Tarih 2. satırda: "Fund Holdings Data as of 08/28/2026"
    with open(dosya_yolu) as f:
        satirlar = f.readlines()
    tarih = pd.to_datetime(satirlar[1].split("as of")[1].strip(),
                           format="%m/%d/%Y")

    df = pd.read_csv(dosya_yolu, skiprows=2)

    # Ticker'ı olmayanlar (yasal metin) ve nakit satırları elenir
    df = df[df["Ticker"].notna()].copy()
    df["weight"] = pd.to_numeric(df["% of Net Assets"], errors="coerce")
    df = df.dropna(subset=["weight"])
    df = df[~df["Ticker"].str.upper().isin(["CASH", "USD"])]

    df["shares"] = pd.to_numeric(
        df["Shares Held"].astype(str).str.replace(",", ""), errors="coerce")
    df["market_value"] = pd.to_numeric(
        df["Market Value ($)"].astype(str).str.replace(",", ""),
        errors="coerce")

    df["weight"] = df["weight"] / df["weight"].sum() * 100

    # AIQ da yabancı borsaları Bloomberg formatında veriyor ("700 HK")
    df["Ticker"] = df["Ticker"].map(bloomberg_ticker)

    df = df[["Ticker", "Name", "shares", "market_value", "weight"]].copy()
    df.columns = ["ticker", "name", "shares", "market_value", "weight"]

    df["cusip"] = None
    df["sector"] = None
    df["location"] = None
    df["figi"] = None
    df["fund"] = fon_adi
    df["date"] = tarih

    return df.reset_index(drop=True)


def parse_roundhill(dosya_yolu, fon_adi):
    df = pd.read_csv(dosya_yolu)

    # Tarih dosya adından: CHAT_ETF_Holdings_08-30-2026.csv (MM-DD-YYYY)
    m = re.search(r"(\d{2})-(\d{2})-(\d{4})", dosya_yolu)
    tarih = (pd.to_datetime(f"{m.group(3)}-{m.group(1)}-{m.group(2)}")
             if m else pd.NaT)

    df = df[df["Ticker"].notna()].copy()
    # döviz/nakit satırlarını at (CNY, EUR, Cash&Other ...)
    df = df[~df["Ticker"].isin(DOVIZ_KODLARI)]
    df = df[~df["Ticker"].str.contains("Cash", case=False, na=False)]
    df["weight"] = pd.to_numeric(
        df["Weight"].astype(str).str.rstrip("%"), errors="coerce")
    df = df.dropna(subset=["weight"])

    df["shares"] = pd.to_numeric(
        df["Shares"].astype(str).str.replace(",", ""), errors="coerce")
    df["market_value"] = pd.to_numeric(
        df["Market Value"].astype(str).str.replace(r"[$,]", "", regex=True),
        errors="coerce")

    df["weight"] = df["weight"] / df["weight"].sum() * 100

    # Yabancı borsalar Bloomberg formatında ("000660 KS" -> "000660.KS")
    df["ticker"] = df["Ticker"].map(bloomberg_ticker)

    df = df[["ticker", "Name", "shares", "market_value", "weight",
             "Identifier"]].copy()
    df.columns = ["ticker", "name", "shares", "market_value", "weight",
                  "cusip"]

    df["sector"] = None
    df["location"] = None
    df["figi"] = None
    df["fund"] = fon_adi
    df["date"] = tarih

    return df.reset_index(drop=True)


if __name__ == "__main__":
    for parser, yol, ad in [
        (parse_vaneck,  "data/raw/SMH_asof_20260827.xlsx", "SMH"),
        (parse_ishares, "data/raw/SOXX_holdings.csv", "SOXX"),
        (parse_spdr,    "data/raw/holdings-daily-us-en-xsd.xlsx", "XSD"),
        (parse_spdr,    "data/raw/holdings-daily-us-en-rokt.xlsx", "ROKT"),
        (parse_vaneck,  "data/raw/SMHX_asof_20260828.xlsx", "SMHX"),
        (parse_invesco, "data/raw/invesco_phlx_semiconductor_etf-Complete_Holdings.csv", "SOXQ"),
        (parse_invesco, "data/raw/invesco_semiconductors_etf-Complete_Holdings.csv", "PSI"),
        (parse_tema,    "data/raw/NASA-holdings-08282026.csv", "NASA"),
        (parse_ishares, "data/raw/IGV_holdings.csv", "IGV"),
        (parse_globalx, "data/raw/aiq_full-holdings_20260828.csv", "AIQ"),
        (parse_roundhill, "data/raw/CHAT_ETF_Holdings_08-30-2026.csv", "CHAT"),
    ]:
        df = parser(yol, ad)
        print(f"{ad}: {len(df)} hisse | toplam ağırlık "
              f"{df['weight'].sum():.4f}% | {df['date'].iloc[0].date()}")
