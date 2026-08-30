
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
