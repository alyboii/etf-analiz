"""Fon holdings dosyalarını en güncel veriye çeker.

Otomatik çekilebilenler (bu script): iShares (SOXX, IGV) ve SPDR (XSD, ROKT) —
sağlayıcı endpoint'leri engelsiz, `asOfDate` boş bırakılınca en güncel gün gelir.

Elle indirilecekler (script hatırlatır): VanEck (SMH, SMHX), Invesco (SOXQ, PSI),
Global X (AIQ), Roundhill (CHAT), Tema (NASA) — siteleri JS-render/oturumlu.

Kullanım:
  python3 guncelle.py            # çekilebilenleri yenile + özet
  python3 guncelle.py --dogrula  # ayrıca dogrula.py çalıştır
  python3 guncelle.py --sektor   # ayrıca sektör haritasını yenile
"""

import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

TARAYICI_UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
               "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36")

# iShares/BlackRock — portfolioId, hedef dosya
ISHARES = {
    "SOXX": (239705, "data/raw/SOXX_holdings.csv"),
    "IGV":  (239771, "data/raw/IGV_holdings.csv"),
}

# SPDR/SSGA — dosya kodu, hedef dosya
SPDR = {
    "XSD":  ("xsd",  "data/raw/holdings-daily-us-en-xsd.xlsx"),
    "ROKT": ("rokt", "data/raw/holdings-daily-us-en-rokt.xlsx"),
}

# Elle indirilecekler: (fon, sağlayıcı, url)
ELLE = [
    ("SMH",  "VanEck",    "https://www.vaneck.com/us/en/investments/"
                          "semiconductor-etf-smh/holdings/"),
    ("SMHX", "VanEck",    "https://www.vaneck.com/us/en/investments/"
                          "fabless-semiconductor-etf-smhx/holdings/"),
    ("SOXQ", "Invesco",   "https://www.invesco.com/us/financial-products/"
                          "etfs/product-detail?ticker=SOXQ"),
    ("PSI",  "Invesco",   "https://www.invesco.com/us/financial-products/"
                          "etfs/product-detail?ticker=PSI"),
    ("AIQ",  "Global X",  "https://www.globalxetfs.com/funds/aiq/"),
    ("CHAT", "Roundhill", "https://www.roundhillinvestments.com/etf/chat/"),
    ("NASA", "Tema",      "https://www.temaetfs.com/nasa"),
]


def _indir(url, hedef, ua=TARAYICI_UA, deneme=3):
    for i in range(deneme):
        try:
            r = urllib.request.Request(url, headers={"User-Agent": ua})
            veri = urllib.request.urlopen(r, timeout=60).read()
            Path(hedef).parent.mkdir(parents=True, exist_ok=True)
            Path(hedef).write_bytes(veri)
            return len(veri)
        except (urllib.error.URLError, TimeoutError):
            if i == deneme - 1:
                raise
            time.sleep(1.5 * (i + 1))


def ishares_url(pid):
    return ("https://www.blackrock.com/varnish-api/blk-one01-product-data"
            "/product-data/api/v1/get-fund-document"
            "?appType=PRODUCT_PAGE&appSubType=ISHARES&targetSite=us-ishares"
            f"&locale=en_US&portfolioId={pid}&userType=individual"
            "&component=holdings")


def spdr_url(kod):
    return ("https://www.ssga.com/us/en/intermediary/library-content/products"
            f"/fund-data/etfs/us/holdings-daily-us-en-{kod}.xlsx")


def _tarih(fon, parser, yol):
    try:
        return str(parser(yol, fon)["date"].iloc[0].date())
    except Exception as e:
        return f"okunamadı ({type(e).__name__})"


def guncelle(log=print):
    from parsers import parse_ishares, parse_spdr

    log("=== Otomatik çekilenler ===")
    for fon, (pid, yol) in ISHARES.items():
        try:
            n = _indir(ishares_url(pid), yol)
            log(f"  {fon:5} iShares  {n:>7}B  -> {_tarih(fon, parse_ishares, yol)}")
        except Exception as e:
            log(f"  {fon:5} iShares  HATA {type(e).__name__}")
        time.sleep(0.3)

    for fon, (kod, yol) in SPDR.items():
        try:
            n = _indir(spdr_url(kod), yol)
            log(f"  {fon:5} SPDR     {n:>7}B  -> {_tarih(fon, parse_spdr, yol)}")
        except Exception as e:
            log(f"  {fon:5} SPDR     HATA {type(e).__name__}")
        time.sleep(0.3)

    log("\n=== Elle indirilecekler (site oturumlu/JS-render) ===")
    log("  Dosyaları data/raw/ altındaki MEVCUT adlarıyla değiştir:")
    for fon, saglayici, url in ELLE:
        log(f"  {fon:5} {saglayici:10} {url}")

    log("\nDXYZ: SEC N-PORT'tan canlı çekiliyor, dosya güncellemesi gerekmez.")


if __name__ == "__main__":
    guncelle()
    if "--sektor" in sys.argv:
        print("\n=== Sektör haritası yenileniyor ===")
        import sektorler
        sektorler.topla()
    if "--dogrula" in sys.argv:
        print("\n=== Doğrulama ===")
        import dogrula
        dogrula.dogrula()
