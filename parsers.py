
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


if __name__ == "__main__":
    for parser, yol, ad in [
        (parse_vaneck,  "data/raw/SMH_asof_20260827.xlsx", "SMH"),
        (parse_ishares, "data/raw/SOXX_holdings.csv", "SOXX"),
        (parse_spdr,    "data/raw/holdings-daily-us-en-xsd.xlsx", "XSD"),
    ]:
        df = parser(yol, ad)
        print(f"{ad}: {len(df)} hisse | toplam ağırlık "
              f"{df['weight'].sum():.4f}% | {df['date'].iloc[0].date()}")
