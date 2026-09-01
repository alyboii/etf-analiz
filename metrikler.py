
import numpy as np
import pandas as pd


def donem_getirisi(fiyat_df, gun, min_oran=0.9):
    """Son 'gun' işlem günündeki yüzde getiri (ticker bazında Seri).

    Pencerede verisi min_oran'dan az olan ticker NaN döner —
    yeni listelenen hisseler yanıltıcı kısmi getiri üretmesin diye.
    """
    p = fiyat_df.iloc[-gun:]
    yeterli = p.notna().sum() >= len(p) * min_oran

    bas = p.apply(lambda s: s.dropna().iloc[0] if s.notna().any() else np.nan)
    son = p.apply(lambda s: s.dropna().iloc[-1] if s.notna().any() else np.nan)

    getiri = (son / bas - 1) * 100
    return getiri.where(yeterli)


def yillik_getiriler(fiyat_df, min_kapsam=0.9):
    """Takvim yılı bazında yüzde getiri (satır: yıl, kolon: ticker).

    O yıl beklenen işlem günlerinin min_kapsam'ından az verisi olan hücre
    NaN döner. Sonradan açılmış fonlarda (SMHX, CHAT) kuruluş yılı tam yıl
    değildir; yan yana konunca tam yıllarla kıyaslanmış gibi görünür.

    Beklenen gün sayısı, o yıl herhangi bir kolonda görülen en yüksek
    gözlem sayısıdır — piyasa takvimini ayrıca bilmeye gerek kalmaz.
    """
    kayit = {}
    for yil, p in fiyat_df.groupby(fiyat_df.index.year):
        sayim = p.notna().sum()
        bas = p.apply(lambda s: s.dropna().iloc[0] if s.notna().any() else np.nan)
        son = p.apply(lambda s: s.dropna().iloc[-1] if s.notna().any() else np.nan)

        getiri = (son / bas - 1) * 100
        kayit[yil] = getiri.where(sayim >= sayim.max() * min_kapsam)

    return pd.DataFrame(kayit).T


def yogunlasma(df):
    """Tek bir fonun holdings tablosundan yoğunlaşma ölçüleri."""
    d = df.sort_values("weight", ascending=False)
    w = d["weight"] / 100
    hhi_pay = (w ** 2).sum()

    return {
        "hisse_sayisi": len(d),
        "en_buyuk": d["weight"].iloc[0],
        "top_3": d["weight"].head(3).sum(),
        "top_10": d["weight"].head(10).sum(),
        "hhi": hhi_pay * 10000,
        "etkin_hisse": 1 / hhi_pay,
    }


def agirlikli_fk(df, pe_map):
    """Fonun F/K'sı: holdings F/K'larının ağırlıklı harmonik ortalaması.

    Piyasa standardı budur (iShares, Vanguard, Morningstar, MSCI aynı
    yöntemi kullanır): F/K = Σw / Σ(w / F/K), yalnızca pozitif F/K'lı
    hisseler üzerinden. Aritmetik ortalama alınmaz — tek bir aşırı çarpan
    sonucu ele geçirir; harmonik ortalama ise portföyün toplam kazanç
    veriminin tersidir, o yüzden ağırlıklarla toplanabilir.

    Zarar eden ya da verisi gelmeyen hisseler dışarıda kalır; ağırlığın ne
    kadarının kapsandığı 'kapsam' (%) ile döner. Kapsam bilgisi olmadan
    rakamı göstermek yanıltıcı olur.
    """
    if not pe_map:
        return {"fk": None, "kapsam": 0.0}

    d = df[["ticker", "weight"]].copy()
    d["pe"] = d["ticker"].map(pe_map)
    gecerli = d[d["pe"].notna() & (d["pe"] > 0)]

    toplam, dahil = d["weight"].sum(), gecerli["weight"].sum()
    if toplam <= 0 or dahil <= 0:
        return {"fk": None, "kapsam": 0.0}

    return {"fk": dahil / (gecerli["weight"] / gecerli["pe"]).sum(),
            "kapsam": dahil / toplam * 100}


def katki(df, getiri_serisi):
    """Katkı = güncel ağırlık × dönem getirisi.

    (katki_df, getirisi hesaplanamayan ticker listesi) döner.
    """
    d = df.copy()
    d["getiri"] = d["ticker"].map(getiri_serisi)

    veri_yok = d[d["getiri"].isna()]["ticker"].tolist()

    d = d.dropna(subset=["getiri"]).copy()
    d["katki"] = (d["weight"] / 100) * d["getiri"]

    return d.sort_values("katki", ascending=False), veri_yok


def risk_metrikleri(seri, risksiz_gunluk=0.0):
    """Tek bir fiyat serisi için getiri, volatilite, maks. düşüş, Sharpe."""
    seri = seri.dropna()
    gunluk = seri.pct_change().dropna()
    fazla = gunluk - risksiz_gunluk

    yillik_vol = gunluk.std() * np.sqrt(252) * 100
    dusus = (seri / seri.cummax() - 1) * 100

    return {
        "getiri": (seri.iloc[-1] / seri.iloc[0] - 1) * 100,
        "volatilite": yillik_vol,
        "max_dusus": dusus.min(),
        "sharpe": (fazla.mean() * 252) / (yillik_vol / 100) if yillik_vol else np.nan,
    }


def yonetim_ucreti(bilgi):
    """Fonun yıllık yönetim ücreti (%) ve değerin alındığı yfinance alanı.

    yfinance ücreti tek bir alanda vermiyor, alanlar sırayla denenir.
    Ayrıca aynı alan kimi fonda kesir (0.0035), kimi fonda yüzde (0.35)
    olarak geliyor. Ayrım şöyle yapılır: kesir varsayılıp 100 ile çarpılır,
    sonuç %3'ü aşıyorsa kaynak zaten yüzdeymiş demektir ve çarpan geri
    alınır. Hiçbir ETF yılda %3 almaz, dolayısıyla ayrım her iki kaynak
    biçimi için de doğru sonuç verir; yalnızca %0,03'ün altındaki bir
    ücret yanlış okunurdu, o da bu fonlarda yok (en ucuzu SOXQ %0,19).

    (None, None) döner: hiçbir alan dolu değilse.
    """
    for alan in ("netExpenseRatio", "annualReportExpenseRatio",
                 "expenseRatio"):
        d = (bilgi or {}).get(alan)
        if d is None or pd.isna(d):
            continue
        yuzde = d * 100
        return (yuzde / 100 if yuzde > 3 else yuzde), alan
    return None, None


def fiyat_istatistikleri(seri, bilgi=None):
    """52 haftalık fiyat aralığı, banddaki konum ve ortalama hacim.

    yfinance künyesi (`yf.Ticker(x).info`) verilmişse yüksek/düşük oradan
    okunur: bu değerler düzeltilmemiş fiyattan gelir, yani kullanıcının
    aracı kurumunda gördüğü rakamla birebir aynıdır. Künye yoksa son 252
    işlem gününün düzeltilmiş kapanışından hesaplanır — temettü düzeltmesi
    yüzünden biraz farklı çıkar, 'kaynak' hangisi olduğunu söyler.

    Hacim fiyat serisinde bulunmadığı için yalnızca künyeden gelir.
    """
    bilgi = bilgi or {}
    seri = seri.dropna()

    yuksek = bilgi.get("fiftyTwoWeekHigh")
    dusuk = bilgi.get("fiftyTwoWeekLow")
    fiyat = bilgi.get("regularMarketPrice") or bilgi.get("previousClose")
    kaynak = "künye"

    if yuksek is None or dusuk is None:
        pencere = seri.iloc[-252:]
        yuksek = pencere.max() if len(pencere) else None
        dusuk = pencere.min() if len(pencere) else None
        kaynak = "kapanış"
    if fiyat is None and len(seri):
        fiyat = seri.iloc[-1]

    band = None
    if not any(v is None or pd.isna(v) for v in (yuksek, dusuk, fiyat)):
        if yuksek > dusuk:
            band = (fiyat - dusuk) / (yuksek - dusuk) * 100

    return {"yuksek_52h": yuksek, "dusuk_52h": dusuk, "fiyat": fiyat,
            "band_konum": band, "ort_hacim": bilgi.get("averageVolume"),
            "kaynak": kaynak}


def drawdown_serisi(seri):
    """Her gün için zirveye göre yüzde düşüş."""
    seri = seri.dropna()
    return (seri / seri.cummax() - 1) * 100


def risksiz_gunluk_oran(seri):
    """Risksiz getiri vekilinden (ör. BIL) günlük ortalama oran.

    Sharpe'ın paydası yıllıklandırılmış volatilite olduğu için burada
    günlük ondalık oran döner; risk_metrikleri bunu doğrudan alır.
    """
    seri = seri.dropna()
    if len(seri) < 2:
        return 0.0
    return seri.pct_change().mean()


def ortusme(holdings):
    """Fonlar arası ikili ağırlık örtüşmesi matrisi (%).

    Örtüşme = iki fonun ortak hisselerinde min(ağırlık) toplamı.
    %100 birebir aynı portföy, %0 hiç ortak hisse yok demek.
    holdings: {fon_adi: holdings DataFrame}
    """
    w = {f: d.groupby("ticker")["weight"].sum() for f, d in holdings.items()}
    fonlar = list(w)

    m = pd.DataFrame(index=fonlar, columns=fonlar, dtype=float)
    for a in fonlar:
        for b in fonlar:
            ortak = w[a].index.intersection(w[b].index)
            m.loc[a, b] = pd.concat([w[a][ortak], w[b][ortak]],
                                    axis=1).min(axis=1).sum()
    return m


def ortak_hisseler(holdings, en_az=None):
    """Birden çok fonda geçen hisselerin ağırlık tablosu.

    en_az: bir hissenin kaç fonda birden bulunması gerektiği
    (varsayılan: hepsinde).
    """
    w = {f: d.groupby("ticker")["weight"].sum() for f, d in holdings.items()}
    tablo = pd.DataFrame(w)

    en_az = en_az or len(w)
    tablo = tablo[tablo.notna().sum(axis=1) >= en_az]

    return tablo.sort_values(list(w)[0], ascending=False)


def gecmis_agirlik(gecmis, fon, tarih):
    """Verilen tarihteki (ya da öncesindeki en yakın) ağırlık anlık görüntüsü.

    (anlik_goruntu_tarihi, DataFrame) döner; hiç kayıt yoksa (None, None).
    """
    d = gecmis[(gecmis["fund"] == fon) & (gecmis["date"] <= tarih)]
    if d.empty:
        return None, None
    en_yakin = d["date"].max()
    return en_yakin, d[d["date"] == en_yakin]


def katki_donem_basi(gecmis, fiyat_df, fon, gun):
    """Dönem BAŞI ağırlıklarıyla katkı — geriye dönük yanlılık olmadan.

    katki() bugünkü ağırlıkları geçmiş getiriye uygular; bu, dönem içinde
    yükselen hisseleri fazla temsil eder. Bu fonksiyon dönemin başındaki
    gerçek ağırlıkları kullanır.

    (katki_df, anlik_goruntu_tarihi, veri_yok) döner.
    """
    pencere = fiyat_df.iloc[-gun:]
    bas_tarih = pencere.index[0]

    w_tarih, w = gecmis_agirlik(gecmis, fon, bas_tarih)
    if w is None:
        return None, None, []

    getiri = donem_getirisi(pencere, len(pencere))

    d = w[["ticker", "name", "weight"]].copy()
    d["getiri"] = d["ticker"].map(getiri)
    veri_yok = d[d["getiri"].isna()]["ticker"].tolist()

    d = d.dropna(subset=["getiri"]).copy()
    d["katki"] = (d["weight"] / 100) * d["getiri"]

    return d.sort_values("katki", ascending=False), w_tarih, veri_yok


def hisse_siralamasi(holdings, ticker):
    """Bir hisseyi en çok tutan fonlar, ağırlığa göre sıralı.

    holdings: {fon_adi: holdings DataFrame}
    Hisseyi tutmayan fonlar sonuçta yer almaz.
    """
    tablo = ortak_hisseler(holdings, en_az=1)
    if ticker not in tablo.index:
        return pd.Series(dtype=float)
    return tablo.loc[ticker].dropna().sort_values(ascending=False)


def _seri_getiri(seri, gun, min_oran=0.9):
    """Tek fiyat serisinde son 'gun' işlem gününün yüzde getirisi.

    Pencerede yeterli veri yoksa (yeni listelenmiş) NaN döner.
    """
    p = seri.dropna()
    if len(p) < 2:
        return np.nan
    p = p.iloc[-gun:]
    if len(p) < gun * min_oran:
        return np.nan
    return (p.iloc[-1] / p.iloc[0] - 1) * 100


def alternatif_getiriler(fiyat_df, fon, para="TL", faiz_yillik=0.45,
                         donemler=None):
    """Fon ve alternatif varlıkların dönem getirileri (tidy DataFrame).

    Kolonlar: donem, varlik, getiri, fon.
    para="TL": USD serileri TRY=X ile liraya çevrilir; dolar=USD/TRY,
               euro=EUR/TRY, faiz=ayarlanabilir TL oranı (piyasa dışı).
    para="USD": her şey USD; euro=EUR/USD, faiz=BIL; "dolar" baz para
                olduğu için çıkarılır.

    fiyat_df: fon, GC=F, SI=F, TRY=X, EURTRY=X, EURUSD=X, BIL ve
    BTC-USD, ETH-USD, XRP-USD kolonlarını içermeli. FX takvimi farklı
    olduğu için önce ffill uygulanır. Kripto 7/24 işlem görür; aşağıdaki
    filtre onu da fonun işlem günlerine indirger, yani hafta sonu
    hareketleri bir sonraki işlem gününde toplu olarak görünür.
    """
    donemler = donemler or {"1 ay": 21, "3 ay": 63, "6 ay": 126, "1 yıl": 252}

    # ÖNCE fonun gerçek işlem günlerine in, SONRA alt kolonları o günlere
    # taşı. Tersi yapılırsa (ffill sonra filtre) fonun fiyatı FX'in işlem
    # gördüğü hafta sonlarına da taşınır ve dönem penceresi kayar.
    df = fiyat_df.loc[fiyat_df[fon].notna()].ffill()

    if para == "TL":
        usdtry = df["TRY=X"]
        varliklar = {
            fon:        df[fon] * usdtry,
            "Altın":    df["GC=F"] * usdtry,
            "Gümüş":    df["SI=F"] * usdtry,
            "Dolar":    usdtry,
            "Euro":     df["EURTRY=X"],
            "Bitcoin":  df["BTC-USD"] * usdtry,
            "Ethereum": df["ETH-USD"] * usdtry,
            "XRP":      df["XRP-USD"] * usdtry,
        }
        faiz_var = True
    else:
        varliklar = {
            fon:        df[fon],
            "Altın":    df["GC=F"],
            "Gümüş":    df["SI=F"],
            "Euro":     df["EURUSD=X"],
            "Bitcoin":  df["BTC-USD"],
            "Ethereum": df["ETH-USD"],
            "XRP":      df["XRP-USD"],
            "Faiz":     df["BIL"],
        }
        faiz_var = False

    kayit = []
    for ad, gun in donemler.items():
        for v, seri in varliklar.items():
            kayit.append({"donem": ad, "varlik": v,
                          "getiri": _seri_getiri(seri, gun)})
        if faiz_var:
            faiz = ((1 + faiz_yillik) ** (gun / 252) - 1) * 100
            kayit.append({"donem": ad, "varlik": "Faiz", "getiri": faiz})

    out = pd.DataFrame(kayit)
    out["fon"] = fon
    return out


def fon_sektor_agirliklari(holdings, harita):
    """{fon: holdings df} + ticker->sektör sözlüğü -> sektör × fon ağırlık (%).

    Satır: sektör, kolon: fon. Ağırlık yüzde olarak toplanır.
    """
    kayit = {}
    for fon, d in holdings.items():
        s = d.copy()
        s["sektor"] = s["ticker"].map(harita).fillna("Diğer")
        kayit[fon] = s.groupby("sektor")["weight"].sum()
    return pd.DataFrame(kayit).fillna(0.0)


def karisim_holdings(holdings, agirliklar):
    """Fon karışımının birleşik portföyü (ticker, name, weight).

    Her fonun hisse ağırlığı, fonun karışımdaki payıyla çarpılır ve ticker
    bazında toplanır: iki fonda da bulunan hisse tek satırda birikir —
    örtüşmenin somut karşılığı budur. agirliklar {fon: yüzde}; toplamı
    100 olmak zorunda değil, normalize edilir.

    Çıktı kolonları yogunlasma() ve fon_sektor_agirliklari() ile uyumlu.
    """
    toplam = sum(agirliklar.values())
    if toplam <= 0:
        return pd.DataFrame(columns=["ticker", "name", "weight"])

    parcalar = []
    for fon, pay in agirliklar.items():
        d = holdings[fon][["ticker", "name", "weight"]].copy()
        d["weight"] = d["weight"] * (pay / toplam)
        parcalar.append(d)

    birlesik = (pd.concat(parcalar, ignore_index=True)
                  .groupby("ticker", as_index=False)
                  .agg(name=("name", "first"), weight=("weight", "sum")))
    return (birlesik.sort_values("weight", ascending=False)
                    .reset_index(drop=True))


def karisim_serisi(fiyat_df, agirliklar):
    """Karışımın sentetik fiyat endeksi (100'den başlar).

    Fonların günlük getirileri ağırlıkla toplanır, kümülatif çarpımla
    endekse çevrilir. VARSAYIM: günlük yeniden dengeleme — her gün
    ağırlıklar hedefe döner. Al-tut bir portföyde kazanan fonun payı
    zamanla kendiliğinden büyür, sonuç bundan farklı çıkar.

    Yalnızca bütün fonların verisi olan günler kullanılır; karışımda yeni
    bir fon varsa seri onun kuruluşundan itibaren başlar.
    """
    toplam = sum(agirliklar.values())
    if toplam <= 0:
        return pd.Series(dtype=float)

    fonlar = list(agirliklar)
    p = fiyat_df[fonlar].dropna()
    if len(p) < 2:
        return pd.Series(dtype=float)

    w = pd.Series({f: agirliklar[f] / toplam for f in fonlar})
    karisim = (p.pct_change().dropna() * w).sum(axis=1)

    # İlk gün 100 olarak eklenir: pct_change ilk satırı düşürüyor, o
    # olmadan endeks bir gün geç başlar ve tek fonlu karışım bile o fonun
    # getirisini birebir vermez.
    bas = pd.Series([100.0], index=[p.index[0]])
    return pd.concat([bas, 100 * (1 + karisim).cumprod()])


def bicim_fiyat(x):
    """Fiyatı Türkçe ondalıkla yazar: 225.64 -> '$225,64'. Yoksa '—'."""
    if x is None or pd.isna(x):
        return "—"
    return "$" + f"{x:,.2f}".translate(str.maketrans({",": ".", ".": ","}))


def bicim_buyuk(x, birim=""):
    """Büyük sayıyı Türkçe kısaltmayla yazar: 1.87e12 -> '1,87 T'.

    Mn = milyon, Mr = milyar, T = trilyon; binlik ayırıcı nokta, ondalık
    virgül. Veri yoksa '—' döner: eksik veri ekranda hata değil boşluktur.
    """
    if x is None or pd.isna(x):
        return "—"

    for esik, kisa in ((1e12, " T"), (1e9, " Mr"), (1e6, " Mn")):
        if abs(x) >= esik:
            metin = f"{x / esik:,.2f}" + kisa
            break
    else:
        metin = f"{x:,.0f}"

    metin = metin.translate(str.maketrans({",": ".", ".": ","}))
    return f"{metin} {birim}".strip()
