"""Geçmiş holdings toplayıcı.

İki kaynak:
  - iShares/BlackRock günlük arşivi (asOfDate ile herhangi bir işlem günü).
    Sadece iShares fonları için; dosya formatı parsers.parse_ishares ile aynı.
  - SEC N-PORT (üç aylık, 2019'dan beri). Her fon için çalışır ama
    ticker vermez; CUSIP/isim/ISIN üzerinden eşlemek gerekir.

Çıktı parsers.py ile aynı şema + "kaynak" kolonu.
"""

import html
import json
import re
import time
import urllib.error
import urllib.request
from pathlib import Path

import pandas as pd

from parsers import parse_ishares

UA = "ETF Analiz Research (github.com/alyboii/etf-analiz)"
TARAYICI_UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
               "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36")

ONBELLEK = Path("data/cache")
CIKTI = Path("data/history")

FON_META = {
    "SMH":  {"cik": 1137360, "seri": "S000034411", "ishares_id": None},
    "SOXX": {"cik": 1100663, "seri": "S000004354", "ishares_id": 239705},
    "XSD":  {"cik": 1064642, "seri": "S000010020", "ishares_id": None},
}

SEMA = ["ticker", "name", "shares", "market_value", "weight",
        "sector", "location", "figi", "cusip", "fund", "date", "kaynak"]


def _sayi(x):
    """N-PORT sayısal alanı; "N/A" ve boş değerler için NaN."""
    try:
        return float(x)
    except (TypeError, ValueError):
        return float("nan")


def _cek(url, ua=UA, deneme=3):
    for i in range(deneme):
        try:
            r = urllib.request.Request(url, headers={"User-Agent": ua})
            return urllib.request.urlopen(r, timeout=60).read()
        except (urllib.error.URLError, TimeoutError) as e:
            if i == deneme - 1:
                raise
            time.sleep(1.5 * (i + 1))


# ---------------------------------------------------------------- iShares

def ishares_url(pid, tarih):
    return ("https://www.blackrock.com/varnish-api/blk-one01-product-data"
            "/product-data/api/v1/get-fund-document"
            "?appType=PRODUCT_PAGE&appSubType=ISHARES&targetSite=us-ishares"
            f"&locale=en_US&portfolioId={pid}&userType=individual"
            f"&component=holdings&asOfDate={tarih:%Y%m%d}")


def ishares_gunluk(fon, tarih):
    """Tek bir işlem gününün holdings'i. İşlem günü değilse None.

    parse_ishares dosya yolu beklediği için indirilen içerik önce
    önbelleğe yazılır, sonra oradan okunur.
    """
    pid = FON_META[fon]["ishares_id"]
    yol = ONBELLEK / fon / f"{tarih:%Y%m%d}.csv"

    if not yol.exists():
        ham = _cek(ishares_url(pid, tarih), ua=TARAYICI_UA)
        # işlem günü değilse tarih satırı "-" gelir, önbelleğe alma
        if b'as of,"-"' in ham[:400]:
            return None
        yol.parent.mkdir(parents=True, exist_ok=True)
        yol.write_bytes(ham)

    d = parse_ishares(str(yol), fon)
    d["kaynak"] = "ishares_gunluk"
    return d


# ------------------------------------------------------------------ N-PORT

def nport_listesi(fon, adet=40):
    """Fonun N-PORT dosyaları: [(dosyalanma_tarihi, accession), ...]"""
    seri = FON_META[fon]["seri"]
    tum = []
    for start in range(0, adet, 40):
        x = _cek("https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany"
                 f"&CIK={seri}&type=NPORT-P&dateb=&owner=include"
                 f"&count=40&start={start}&output=atom").decode("utf-8", "replace")
        acc = re.findall(r"<accession-n[uo]mb?er>(.*?)</accession-n", x)
        fd = re.findall(r"<filing-date>(.*?)</filing-date>", x)
        if not acc:
            break
        tum += list(zip(fd, acc))
        time.sleep(0.2)
    return tum


def nport_holdings(fon, accession, varlik_tipleri=("EC",), cik=None):
    """N-PORT XML'inden pozisyonlar. (donem, DataFrame) döner.

    varlik_tipleri: tutulacak assetCat değerleri. Varsayılan sadece "EC"
      (adi hisse) — ETF geçmişi için doğru davranış.
      None verilirse hiçbir filtre uygulanmaz; DXYZ gibi fonlarda pozisyonlar
      SPV/LLC olduğu için assetCat ya boş ya "EP" gelir, filtre uygulanırsa
      Anthropic dahil çoğu pozisyon düşer.
    cik: FON_META'da olmayan fonlar için doğrudan verilebilir.
    """
    cik = cik or FON_META[fon]["cik"]
    a = accession.replace("-", "")
    yol = ONBELLEK / fon / f"nport_{a}.xml"

    if yol.exists():
        x = yol.read_text("utf-8", "replace")
    else:
        x = _cek(f"https://www.sec.gov/Archives/edgar/data/{cik}/{a}"
                 "/primary_doc.xml").decode("utf-8", "replace")
        yol.parent.mkdir(parents=True, exist_ok=True)
        yol.write_text(x)

    donem = re.search(r"<repPdDate>([^<]+)", x).group(1)

    rows = []
    for b in re.findall(r"<invstOrSec>(.*?)</invstOrSec>", x, re.S):
        al = lambda t: (re.search(rf"<{t}>([^<]*)", b) or [None, None])[1]
        tip = al("assetCat")
        if varlik_tipleri is not None and tip not in varlik_tipleri:
            continue
        isin = re.search(r'<isin value="([^"]*)"', b)
        rows.append({
            "name": html.unescape(al("name") or ""),
            "cusip": al("cusip"),
            "isin": isin.group(1) if isin else None,
            # özel şirket pozisyonlarında "N/A" gelebiliyor
            "shares": _sayi(al("balance")),
            "market_value": _sayi(al("valUSD")),
            "weight": _sayi(al("pctVal")),
            "varlik_tipi": tip or "",
        })

    d = pd.DataFrame(rows)
    if len(d):
        d["weight"] = d["weight"] / d["weight"].sum() * 100
    return donem, d


# ------------------------------------------------------- ticker eşlemesi

def _anahtar(s):
    s = re.sub(r"[^a-z ]", " ", html.unescape(str(s)).lower())
    at = {"inc", "corp", "corporation", "co", "ltd", "plc", "nv", "sa", "ag",
          "the", "class", "a", "b", "c", "holdings", "holding", "group",
          "technologies", "technology", "tech", "systems", "adr", "limited",
          "company", "sp"}
    return " ".join(sorted(w for w in s.split() if w and w not in at))


def openfigi(isinler):
    """ISIN -> ticker (ABD borsaları). Anahtarsız kotayı aşmamak için 10'arlı."""
    bulunan = {}
    for i in range(0, len(isinler), 10):
        parca = isinler[i:i + 10]
        req = urllib.request.Request(
            "https://api.openfigi.com/v3/mapping",
            data=json.dumps([{"idType": "ID_ISIN", "idValue": x}
                             for x in parca]).encode(),
            headers={"Content-Type": "application/json", "User-Agent": UA})
        try:
            cevap = json.load(urllib.request.urlopen(req, timeout=30))
        except Exception:
            continue
        for isin, c in zip(parca, cevap):
            d = [y for y in c.get("data", [])
                 if y.get("exchCode") in ("US", "UN", "UW", "UQ", "UA", "UR")]
            if d:
                bulunan[isin] = d[0]["ticker"]
        time.sleep(3)      # anahtarsız limit: 25 istek/dakika
    return bulunan


def ticker_esle(d, cusip2t, isim2t):
    """CUSIP -> isim -> OpenFIGI sırasıyla ticker doldur."""
    d = d.copy()
    d["ticker"] = d["cusip"].map(cusip2t)

    bos = d["ticker"].isna()
    d.loc[bos, "ticker"] = d.loc[bos, "name"].map(
        lambda n: isim2t.get(_anahtar(n)))

    kalan = d[d["ticker"].isna() & d["isin"].notna()]["isin"].unique().tolist()
    if kalan:
        d["ticker"] = d["ticker"].fillna(d["isin"].map(openfigi(kalan)))
    return d


# ---------------------------------------------------------- orkestrasyon

def islem_gunleri(bas, son):
    """SOXX'un fiyat serisinden gerçek işlem günleri."""
    import yfinance as yf
    px = yf.download("SOXX", start=bas, end=son, auto_adjust=True,
                     progress=False)
    return px.index


def referans_sozlukler(gunlukler):
    """CUSIP->ticker ve isim->ticker sözlükleri.

    Günlük dosyaların tamamından kurulur; böylece portföyden çıkmış
    isimler de eşleşir (N-PORT'ta ticker yok).
    """
    from parsers import parse_spdr, parse_vaneck

    parcalar = list(gunlukler)
    parcalar += [
        parse_vaneck("data/raw/SMH_asof_20260827.xlsx", "SMH"),
        parse_spdr("data/raw/holdings-daily-us-en-xsd.xlsx", "XSD"),
    ]
    hepsi = pd.concat(parcalar, ignore_index=True)

    cusip2t = {c: t for c, t in zip(hepsi["cusip"], hepsi["ticker"])
               if pd.notna(c) and pd.notna(t)}
    isim2t = {_anahtar(n): t for n, t in zip(hepsi["name"], hepsi["ticker"])
              if pd.notna(t)}
    return cusip2t, isim2t


def topla(yil=5, gunluk_fonlar=("SOXX",), log=print):
    """Geçmiş holdings'i toplar ve data/history/holdings.parquet'e yazar."""
    son = pd.Timestamp.today().normalize()
    bas = son - pd.DateOffset(months=round(yil * 12))

    # --- 1) günlük (iShares) ---
    gunlukler = []
    for fon in gunluk_fonlar:
        gunler = islem_gunleri(bas, son + pd.Timedelta(days=1))
        log(f"{fon}: {len(gunler)} işlem günü taranacak")
        atlanan = 0
        for i, g in enumerate(gunler, 1):
            try:
                d = ishares_gunluk(fon, g)
            except Exception as e:
                log(f"  {g:%Y-%m-%d} HATA {type(e).__name__}")
                atlanan += 1
                continue
            if d is None:
                atlanan += 1
            else:
                gunlukler.append(d)
            if i % 100 == 0:
                log(f"  {i}/{len(gunler)} ({len(gunlukler)} alındı, "
                    f"{atlanan} atlandı)")
            time.sleep(0.25)
        log(f"{fon}: {len(gunlukler)} günlük anlık görüntü")

    # --- 2) ticker sözlükleri ---
    cusip2t, isim2t = referans_sozlukler(gunlukler)
    log(f"sözlük: {len(cusip2t)} cusip, {len(isim2t)} isim")

    # --- 3) çeyreklik (N-PORT) ---
    nportlar = []
    for fon in FON_META:
        for fd, acc in nport_listesi(fon):
            if pd.Timestamp(fd) < bas - pd.DateOffset(months=4):
                continue
            try:
                donem, d = nport_holdings(fon, acc)
            except Exception as e:
                log(f"  {fon} {acc} HATA {type(e).__name__}")
                continue
            if not len(d) or pd.Timestamp(donem) < bas:
                continue
            d = ticker_esle(d, cusip2t, isim2t)
            d["fund"] = fon
            d["date"] = pd.Timestamp(donem)
            d["kaynak"] = "nport"
            d["sector"] = None
            d["location"] = None
            d["figi"] = None
            nportlar.append(d)
            time.sleep(0.2)
        log(f"{fon}: {sum(x['fund'].iloc[0]==fon for x in nportlar)} çeyreklik")

    # --- 4) birleştir ---
    hepsi = pd.concat(gunlukler + nportlar, ignore_index=True)
    hepsi = hepsi.reindex(columns=SEMA)

    # ticker'ı eşleşmeyenler düşer; ne kadarını kaybettiğimizi kaydet
    toplam = hepsi.groupby(["fund", "date", "kaynak"])["weight"].sum()
    hepsi = hepsi.dropna(subset=["ticker"])
    kalan = hepsi.groupby(["fund", "date", "kaynak"])["weight"].sum()
    kapsam = (kalan / toplam * 100).rename("kapsam")

    # aynı fon-gün hem günlük hem N-PORT'ta varsa günlüğü tut
    oncelik = {"ishares_gunluk": 0, "nport": 1}
    hepsi["_o"] = hepsi["kaynak"].map(oncelik)
    hepsi = (hepsi.sort_values("_o")
                  .drop_duplicates(["fund", "date", "ticker"], keep="first")
                  .drop(columns="_o"))

    # eşleşmeyenler düştüğü için ağırlığı 100'e geri ölçekle
    hepsi["weight"] = (hepsi["weight"]
                       / hepsi.groupby(["fund", "date"])["weight"]
                              .transform("sum") * 100)

    hepsi = hepsi.merge(kapsam.reset_index(), on=["fund", "date", "kaynak"],
                        how="left")
    hepsi = hepsi.sort_values(["fund", "date", "weight"],
                              ascending=[True, True, False])

    dusuk = kapsam[kapsam < 99].round(2)
    if len(dusuk):
        log(f"\nkapsamı %99'un altında olan {len(dusuk)} anlık görüntü:")
        log(dusuk.to_string())

    CIKTI.mkdir(parents=True, exist_ok=True)
    yol = CIKTI / "holdings.parquet"
    hepsi.to_parquet(yol, index=False)
    log(f"\nyazıldı: {yol}  ({len(hepsi)} satır)")
    return hepsi


if __name__ == "__main__":
    topla()


# -------------------------------------------------------------------- DXYZ

DXYZ_CIK = 1843974          # Destiny Tech100 Inc. (kapalı uçlu fon)
NAKIT_TIPLERI = ("STIV",)   # kısa vadeli hazine/para piyasası


def dxyz_holdings():
    """Destiny Tech100 (DXYZ) en son N-PORT pozisyonları.

    ETF'lerden farklı: pozisyonlar özel şirketlere maruziyet veren SPV/LLC
    yapıları, ticker yok. Bu yüzden fiyat/getiri/katkı hesaplanamaz —
    sadece isim + ağırlık + tip.

    (donem, DataFrame) döner; "nakit" kolonu para piyasası satırını işaretler.
    """
    sub = json.loads(_cek(
        f"https://data.sec.gov/submissions/CIK{DXYZ_CIK:010d}.json").decode())
    r = sub["filings"]["recent"]
    acc = next(a for f, a in zip(r["form"], r["accessionNumber"])
               if f.startswith("NPORT"))

    donem, d = nport_holdings("DXYZ", acc, varlik_tipleri=None, cik=DXYZ_CIK)
    d["nakit"] = d["varlik_tipi"].isin(NAKIT_TIPLERI)

    d["sirket"] = d["name"].map(_sirket_adi)
    return donem, d.sort_values("weight", ascending=False).reset_index(drop=True)


# enstrüman tanımlarını isimden ayıklamak için: aynı şirket farklı hisse
# sınıfı / seri ile birden çok satırda geçiyor (OpenAI, Klarna, Axiom Space...)
_ENSTRUMAN = re.compile(
    r"\s*[,.]?\s*(?:"
    r"Class\s+[A-Z0-9-]+|"
    r"Series\s+[A-Z0-9-]+|"
    r"Common|Preferred|Ordinary|"
    r"Profit\s+Participation\s+Units|Stock|Shares|Units|"
    r"subordinated\s+convertible\s+promissory\s+note.*"
    r")\b", re.I)


def _sirket_adi(ad):
    """SPV/enstrüman gürültüsünü ayıklayıp asıl şirket adını döndürür.

    "Magnitude ANC III, LLC (economic exposure to Anthropic PBC Series B
    Preferred Shares)" -> "Anthropic PBC"
    """
    m = re.search(r"(?:exposure to|invested in)\s+(.+?)\)?$", ad, re.I)
    s = m.group(1) if m else ad.split(" - ")[0]

    onceki = None
    while onceki != s:                 # ekler zincirleme olabiliyor
        onceki = s
        s = _ENSTRUMAN.sub("", s).strip(" .,)")
    return s
