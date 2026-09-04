from pathlib import Path

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
import yfinance as yf

from parsers import (parse_vaneck, parse_ishares, parse_spdr,
                     parse_invesco, parse_tema, parse_globalx,
                     parse_roundhill)
from metrikler import (donem_getirisi, yogunlasma, katki,
                       risk_metrikleri, risksiz_gunluk_oran,
                       ortusme, ortak_hisseler, katki_donem_basi,
                       hisse_siralamasi, alternatif_getiriler,
                       fon_sektor_agirliklari, portfoy_serisi,
                       korelasyon, yillik_getiriler)
import sektorler

st.set_page_config(page_title="ETF Analiz", layout="wide")

FONLAR = {
    "Yarı iletken": {
        "SMH":  (parse_vaneck,  "data/raw/SMH_asof_20260827.xlsx"),
        "SOXX": (parse_ishares, "data/raw/SOXX_holdings.csv"),
        "XSD":  (parse_spdr,    "data/raw/holdings-daily-us-en-xsd.xlsx"),
        "SMHX": (parse_vaneck,  "data/raw/SMHX_asof_20260828.xlsx"),
        "SOXQ": (parse_invesco,
                 "data/raw/invesco_phlx_semiconductor_etf-"
                 "Complete_Holdings.csv"),
        "PSI":  (parse_invesco,
                 "data/raw/invesco_semiconductors_etf-"
                 "Complete_Holdings.csv"),
    },
    "Uzay": {
        "ROKT": (parse_spdr, "data/raw/holdings-daily-us-en-rokt.xlsx"),
        "NASA": (parse_tema, "data/raw/NASA-holdings-08282026.csv"),
        # UFO: procureetfs.com Cloudflare arkasında; dosya elle indirilmeli
    },
    "Yapay Zeka": {
        "IGV":  (parse_ishares, "data/raw/IGV_holdings.csv"),
        "AIQ":  (parse_globalx, "data/raw/aiq_full-holdings_20260828.csv"),
        "CHAT": (parse_roundhill,
                 "data/raw/CHAT_ETF_Holdings_08-30-2026.csv"),
    },
}

# Fon kimlik bilgisi: tam ad, sağlayıcı, gider oranı (%), ne izlediği.
# Gider oranları sağlayıcı sitelerinden doğrulandı (Eylül 2026).
FON_BILGI = {
    "SMH":  ("VanEck Yarı İletken ETF", "VanEck", 0.35,
             "ABD yarı iletken üreticileri (piyasa değeri ağırlıklı, NVIDIA yoğun)"),
    "SOXX": ("iShares Yarı İletken ETF", "iShares", 0.33,
             "PHLX yarı iletken endeksi (30 hisse)"),
    "XSD":  ("SPDR S&P Yarı İletken ETF", "State Street", 0.35,
             "ABD yarı iletken — eşit ağırlıklı (daha dağıtık)"),
    "SMHX": ("VanEck Fabless Yarı İletken ETF", "VanEck", 0.35,
             "Üretimi dışarıya veren (fabless) tasarım şirketleri"),
    "SOXQ": ("Invesco PHLX Yarı İletken ETF", "Invesco", 0.19,
             "PHLX yarı iletken — en düşük maliyetli"),
    "PSI":  ("Invesco Yarı İletken ETF", "Invesco", 0.56,
             "ABD yarı iletken (momentum/kalite seçimli)"),
    "ROKT": ("SPDR Kensho Final Frontiers ETF", "State Street", 0.45,
             "Uzay + derin deniz keşfi teknolojileri"),
    "NASA": ("Tema Space Innovators ETF", "Tema", 0.75,
             "Küresel uzay ekonomisi (yabancı borsalar dahil)"),
    "IGV":  ("iShares Genişletilmiş Yazılım ETF", "iShares", 0.38,
             "ABD yazılım şirketleri (Palantir, Microsoft, Salesforce)"),
    "AIQ":  ("Global X Yapay Zeka & Teknoloji ETF", "Global X", 0.68,
             "Yapay zeka ve büyük teknoloji, küresel"),
    "CHAT": ("Roundhill Üretken Yapay Zeka ETF", "Roundhill", 0.75,
             "Üretken yapay zeka odaklı (küresel)"),
}

DONEMLER = {"1 ay": 21, "3 ay": 63, "6 ay": 126, "1 yıl": 252,
            "3 yıl": 756, "5 yıl": 1260}

# Alternatif karşılaştırma her zaman bu dört dönemi birlikte gösterir
DONEMLER_ALT = {"1 ay": 21, "3 ay": 63, "6 ay": 126, "1 yıl": 252}

# Alternatif varlık renkleri (fon rengi çalışma anında eklenir)
ALT_RENK = {"Altın": "#f1c40f", "Gümüş": "#95a5a6", "Dolar": "#27ae60",
            "Euro": "#8e44ad", "Faiz": "#e67e22"}

RISKSIZ = "BIL"      # kısa vadeli hazine ETF'i, Sharpe'ın risksiz oranı
GOSTERGE = "^GSPC"   # S&P 500
NASDAQ = "^IXIC"     # Nasdaq Composite
BITCOIN = "BTC-USD"  # korelasyon karşılaştırması için
KORELASYON_VARLIK = [BITCOIN, NASDAQ, GOSTERGE]  # fon ile karşılaştırılanlar

# Alternatif yatırım karşılaştırması için (TL/USD bazlı)
ALT_TICKER = ("GC=F", "SI=F", "TRY=X", "EURTRY=X", "EURUSD=X", "BIL")


@st.cache_data
def holdings_yukle(fon, tema):
    parser, yol = FONLAR[tema][fon]
    return parser(yol, fon)


@st.cache_data
def tum_holdings(tema):
    return {f: holdings_yukle(f, tema) for f in FONLAR[tema]}


@st.cache_data
def her_fon():
    """Tüm temalardaki bütün fonlar — hisse bazlı sıralama için."""
    return {f: holdings_yukle(f, t)
            for t in FONLAR for f in FONLAR[t]}


@st.cache_data
def dxyz_yukle():
    """Destiny Tech100 pozisyonları (SEC N-PORT). Ağ hatasında None."""
    try:
        from gecmis import dxyz_holdings
        return dxyz_holdings()
    except Exception as e:
        return ("hata", str(e))


@st.cache_data
def fiyat_yukle(tickerlar):
    """Fiyat serileri; günlük disk önbelleğiyle (data/cache/fiyat_<gün>.parquet).

    İlk açılışta yavaş yfinance indirmesini azaltır: aynı gün tekrar açılışta
    (konteyner yeniden başlasa bile) önbellekten okur, sadece eksik tickerları
    indirir.
    """
    tickerlar = tuple(dict.fromkeys(tickerlar))  # tekrarları at, sırayı koru
    yol = Path("data/cache") / f"fiyat_{pd.Timestamp.today():%Y%m%d}.parquet"
    try:
        onbellek = pd.read_parquet(yol) if yol.exists() else pd.DataFrame()
    except Exception:
        onbellek = pd.DataFrame()

    eksik = [t for t in tickerlar if t not in onbellek.columns]
    if eksik:
        yeni = yf.download(eksik, start="2019-01-01",
                           auto_adjust=True, progress=False)["Close"]
        if isinstance(yeni, pd.Series):
            yeni = yeni.to_frame(eksik[0])
        onbellek = yeni if onbellek.empty else onbellek.join(yeni, how="outer")
        try:
            yol.parent.mkdir(parents=True, exist_ok=True)
            onbellek.to_parquet(yol)
        except Exception:
            pass

    var = [t for t in tickerlar if t in onbellek.columns]
    return onbellek[var].dropna(how="all")


@st.cache_data
def gecmis_yukle():
    """Geçmiş holdings (gecmis.py ile toplanır). Yoksa None."""
    yol = Path("data/history/holdings.parquet")
    return pd.read_parquet(yol) if yol.exists() else None


@st.cache_data
def alt_fiyat_yukle():
    """Alternatif varlık fiyatları (altın, gümüş, USD/TRY, EUR...)."""
    df = yf.download(list(ALT_TICKER), start="2019-01-01",
                     auto_adjust=True, progress=False)["Close"]
    return df.dropna(how="all")


@st.cache_data
def sektor_yukle():
    """Ticker -> Türkçe sektör sözlüğü. Yoksa boş."""
    return sektorler.yukle()


def snapshot_notu(holdings):
    """Fonların 'as of' tarihlerini gösterir; farklıysa uyarır.

    holdings: {fon: holdings DataFrame}
    """
    tarihler = {f: d["date"].iloc[0].date() for f, d in holdings.items()}
    benzersiz = sorted(set(tarihler.values()))
    ozet = ", ".join(f"{f} {t:%d.%m}" for f, t in tarihler.items())
    if len(benzersiz) == 1:
        st.caption(f"Holdings tarihi: {benzersiz[0]:%d.%m.%Y} (tüm fonlar).")
    else:
        st.warning(
            f"⚠️ Fonların holdings tarihleri farklı: {ozet}. "
            "Ağırlıklar aynı güne ait değil. Güncellemek için "
            "`python3 guncelle.py` (otomatik fonlar) ve elle indirilenler.")


def dxyz_goster(donem_adi, gun):
    """DXYZ (Destiny Tech100) — ticker'sız özel şirket maruziyeti görünümü."""
    st.title("DXYZ — Destiny Tech100")
    st.caption("Yapay Zeka teması · Anthropic, SpaceX, OpenAI gibi **borsada "
               "olmayan** özel şirketlere dolaylı erişim.")

    sonuc = dxyz_yukle()
    if sonuc[0] == "hata":
        st.error(f"SEC verisi alınamadı: {sonuc[1]}")
        return

    donem, dx = sonuc
    st.caption(f"SEC N-PORT dönemi: {donem} — veri üç aylık ve ~60 gün gecikmeli.")
    st.warning(
        "DXYZ bir ETF değil, kapalı uçlu fon. Pozisyonları özel şirketlere "
        "maruziyet veren SPV/LLC yapıları ve **ticker'ları yok** — bu yüzden "
        "hisse bazlı getiri, katkı ve risk metrikleri hesaplanamıyor. Aşağıda "
        "sadece isim ve ağırlık var.")

    nakit = dx[dx["nakit"]]["weight"].sum()
    d1, d2, d3 = st.columns(3)
    d1.metric("Pozisyon", len(dx))
    d2.metric("Nakit / para piyasası", f"%{nakit:.1f}")
    d3.metric("Özel şirket maruziyeti", f"%{100 - nakit:.1f}")

    birlesik = (dx[~dx["nakit"]].groupby("sirket")["weight"].sum()
                  .sort_values(ascending=False))
    st.subheader("Şirket bazında maruziyet")
    st.caption("Aynı şirkete birden fazla SPV üzerinden yatırım yapılabiliyor; "
               "burada toplanmış hâli. Anthropic kırmızı ile vurgulu.")
    ust = birlesik.head(15)
    figd = px.bar(x=ust.values, y=ust.index, orientation="h",
                  labels={"x": "Fon içindeki ağırlık (%)", "y": ""},
                  text=[f"%{v:.2f}" for v in ust.values])
    figd.update_traces(
        marker_color=["#c0392b" if "Anthropic" in s else "#1f77b4"
                      for s in ust.index],
        textposition="outside")
    figd.update_layout(height=90 + 34 * len(ust),
                       yaxis=dict(autorange="reversed"), margin=dict(t=10, r=70))
    st.plotly_chart(figd, use_container_width=True)

    with st.expander("Ham pozisyonlar (SPV isimleriyle)"):
        st.dataframe(dx[["name", "sirket", "weight", "varlik_tipi", "nakit"]]
                     .round(3), use_container_width=True)

    st.subheader(f"DXYZ fiyat performansı — {donem_adi}")
    dxf = fiyat_yukle(("DXYZ", GOSTERGE))
    if "DXYZ" in dxf and dxf["DXYZ"].notna().any():
        p = dxf.iloc[-gun:]
        figp = go.Figure()
        for t, ad, renk in [("DXYZ", "DXYZ", "#c0392b"),
                            (GOSTERGE, "S&P 500", "#999999")]:
            s = p[t].dropna()
            if len(s) < 2:
                continue
            figp.add_trace(go.Scatter(
                x=s.index, y=(s / s.iloc[0] - 1) * 100, name=ad,
                line=dict(color=renk, width=2)))
        figp.update_layout(height=380, yaxis_title=f"{donem_adi} (%)",
                           hovermode="x unified", margin=dict(t=10))
        st.plotly_chart(figp, use_container_width=True)
    else:
        st.info("DXYZ fiyat verisi alınamadı.")


# --- Kenar çubuğu ---
st.sidebar.title("ETF Analiz")
tema = st.sidebar.radio("Tema", [t for t in FONLAR if FONLAR[t]])
# DXYZ (özel şirket fonu) Yapay Zeka temasında ayrı bir seçenek
fon_secenek = list(FONLAR[tema].keys())
if tema == "Yapay Zeka":
    fon_secenek = fon_secenek + ["DXYZ"]
fon = st.sidebar.radio("Fon", fon_secenek)
donem_adi = st.sidebar.selectbox("Dönem", list(DONEMLER.keys()), index=1)
gun = DONEMLER[donem_adi]

st.sidebar.caption("Fon metrikleri USD bazlıdır.")
st.sidebar.caption(f"Sharpe'ta risksiz oran: {RISKSIZ}")

st.sidebar.divider()
faiz_yillik = st.sidebar.number_input(
    "Yıllık TL faizi (%)", min_value=0.0, max_value=200.0,
    value=45.0, step=1.0,
    help="Alternatif karşılaştırmada 'faiz' için varsayım. "
         "Piyasa verisi değil, güncel mevduat oranına göre değiştirin.")

with st.expander("ℹ️ Bu dashboard nasıl kullanılır?"):
    st.markdown(
        "Yarı iletken, uzay ve yapay zeka temalı ETF'leri (borsada işlem gören "
        "fon sepetleri) karşılaştırır. Soldan **tema** ve **fon** seç, **dönem** "
        "ayarla.\n\n"
        "- **Fon detayı** — seçili fonun içi: ne tuttuğu, getirisi, riski, "
        "endekslerle ve alternatif yatırımlarla (altın/dolar/faiz) karşılaştırması.\n"
        "- **Karşılaştırma** — aynı temadaki fonlar yan yana.\n"
        "- **Hisse bazlı** — bir hisseyi (ör. NVIDIA) en çok hangi fon tutuyor.\n"
        "- **Portföy simülatörü** — kendi karışımını kurup geçmişte ne "
        "getireceğini gör.\n\n"
        "Fon getirileri **USD** bazlıdır; alternatif ve portföy bölümlerinde "
        "TL/USD seçilebilir. **Bu araç bilgilendirme amaçlıdır, yatırım "
        "tavsiyesi değildir.**")

(detay_sekme, karsilastirma_sekme, hisse_sekme,
 portfoy_sekme) = st.tabs(
    ["Fon detayı", "Karşılaştırma", "Hisse bazlı", "Portföy simülatörü"])


# =====================================================================
# Fon detayı
# =====================================================================
with detay_sekme:
    if fon == "DXYZ":
        dxyz_goster(donem_adi, gun)
    else:
        h = holdings_yukle(fon, tema)

        # geçmiş holdings'teki ticker'lar da lazım: portföyden çıkmış hisseler
        # olmadan dönem başı katkısı eksik hesaplanır
        gec_tum = gecmis_yukle()
        eski = ()
        if gec_tum is not None:
            eski = tuple(sorted(set(gec_tum[gec_tum["fund"] == fon]["ticker"])
                                - set(h["ticker"])))

        # NOT: BTC hafta sonu da işlem gördüğü için ANA çerçeveye eklenmez
        # (indekse hafta sonu satırı ekleyip donem_getirisi kapsamını bozuyor).
        # Korelasyon için ayrı çekilir.
        fiyat = fiyat_yukle(tuple(h["ticker"]) + eski
                            + (fon, GOSTERGE, NASDAQ, RISKSIZ))
        getiri = donem_getirisi(fiyat, gun)

        st.title(f"{fon} — {donem_adi}")
        # --- Kimlik kartı ---
        if fon in FON_BILGI:
            ad, saglayici, gider, izler = FON_BILGI[fon]
            st.markdown(f"**{ad}** · {saglayici} · Gider oranı **%{gider}**")
            st.caption(f"Ne izliyor: {izler}  ·  Holdings tarihi: "
                       f"{h['date'].iloc[0].date()}")
        else:
            st.caption(f"Holdings tarihi: {h['date'].iloc[0].date()}")

        y = yogunlasma(h)
        risksiz = risksiz_gunluk_oran(fiyat[RISKSIZ].iloc[-gun:])
        r = risk_metrikleri(fiyat[fon].iloc[-gun:], risksiz)

        st.caption("Portföy yapısı")
        k1, k2, k3, k4, k5 = st.columns(5)
        k1.metric("Hisse sayısı", y["hisse_sayisi"],
                  help="Fonun tuttuğu farklı hisse sayısı.")
        k2.metric("Etkin hisse", f"{y['etkin_hisse']:.1f}",
                  help="Ağırlıklar hesaba katılınca 'gerçekte' kaç hisseye "
                       "yayıldığı. Yüksek = daha dağıtık, düşük = birkaç hisseye "
                       "yığılmış.")
        k3.metric("En büyük pozisyon", f"%{y['en_buyuk']:.1f}",
                  help="En büyük tek hissenin fon içindeki ağırlığı.")
        k4.metric("İlk 10 ağırlığı", f"%{y['top_10']:.1f}",
                  help="En büyük 10 hissenin toplam ağırlığı. Yüksekse fon "
                       "birkaç hisseye yoğunlaşmış.")
        k5.metric("HHI", f"{y['hhi']:.0f}",
                  help="Yoğunlaşma endeksi (ağırlıkların kareleri toplamı). "
                       "Yükseldikçe fon daha az hisseye yığılmış; 10000 = tek hisse.")

        st.caption(f"Risk ve getiri — {donem_adi}")
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Getiri", f"%{r['getiri']:.1f}",
                  help="Seçili dönemdeki fiyat getirisi (USD).")
        m2.metric("Volatilite (yıllık)", f"%{r['volatilite']:.1f}",
                  help="Yıllıklandırılmış oynaklık; risk ölçüsü. Yüksekse fiyat "
                       "daha çok zıplıyor.")
        m3.metric("Sharpe", f"{r['sharpe']:.2f}",
                  help="Risk başına getiri (fazla getiri ÷ oynaklık). "
                       "Yüksek/pozitif iyi, negatif = riske değmemiş.")
        m4.metric("Maks. düşüş (dönem içi)", f"%{r['max_dusus']:.1f}",
                  help="Dönem içinde zirveden en dibe yaşanan en büyük kayıp.")

        # genç fon: seçilen dönem fonun geçmişinden uzunsa dürüstçe belirt
        mevcut_gun = int(fiyat[fon].notna().sum())
        if mevcut_gun < gun * 0.95:
            st.caption(f"⚠️ {fon} yalnızca ~{mevcut_gun/252:.1f} yıllık; "
                       f"'{donem_adi}' yerine mevcut tüm geçmiş gösteriliyor.")
        elif gun <= 21:
            st.caption("ℹ️ Kısa dönemde Sharpe ve volatilite istatistiksel "
                       "olarak gürültülüdür.")

        st.divider()

        # --- "Ne alırsın" sade özet ---
        st.subheader(f"{fon} alırsan ne alırsın?")
        enb = h.nlargest(5, "weight")
        ilk3 = h.nlargest(3, "weight")["weight"].sum()
        satir = " · ".join(f"**%{w:.0f}** {t}"
                           for t, w in zip(enb["ticker"], enb["weight"]))
        st.markdown(
            f"Yatırdığın her 100 birimin: {satir} … olarak dağılır. "
            f"En büyük **3 hisse** paranın **%{ilk3:.0f}**'ını oluşturur; "
            f"fon toplam **{y['hisse_sayisi']} hisse** tutuyor.")

        # --- Treemap ---
        st.subheader("Portföy dağılımı")
        d = h.copy()
        d["getiri"] = d["ticker"].map(getiri)

        fig = px.treemap(
            d, path=[px.Constant(fon), "ticker"], values="weight",
            color="getiri", color_continuous_midpoint=0,
            color_continuous_scale=["#c0392b", "#eeeeee", "#27ae60"],
            custom_data=["name", "weight", "getiri"],
        )
        fig.update_traces(
            texttemplate="<b>%{label}</b><br>%{customdata[1]:.1f}%",
            hovertemplate="<b>%{customdata[0]}</b><br>Ağırlık: %{customdata[1]:.2f}%"
                          f"<br>{donem_adi}: " + "%{customdata[2]:.1f}%<extra></extra>",
        )
        fig.update_layout(height=500, margin=dict(t=10, l=0, r=0, b=0))
        st.plotly_chart(fig, use_container_width=True)

        # --- Katkı ---
        st.subheader("Getiriye katkı")

        kdf_bas, w_tarih, vy_bas = (None, None, [])
        if gec_tum is not None:
            kdf_bas, w_tarih, vy_bas = katki_donem_basi(gec_tum, fiyat, fon, gun)

        if kdf_bas is not None:
            yontem = st.radio(
                "Ağırlık", ["Dönem başı (doğru)", "Güncel (yaklaşık)"],
                horizontal=True, label_visibility="collapsed")
            donem_basi = yontem.startswith("Dönem başı")
        else:
            donem_basi = False
            st.caption("Geçmiş holdings yok — `python3 gecmis.py` ile toplanabilir.")

        if donem_basi:
            kdf, veri_yok = kdf_bas, vy_bas
            st.caption(f"Katkı = {w_tarih:%d.%m.%Y} ağırlıkları × dönem getirisi.")
        else:
            kdf, veri_yok = katki(h, getiri)
            st.caption("Katkı = **güncel** ağırlık × dönem getirisi. "
                       "Dönem içinde yükselen hisseleri fazla temsil eder.")

        # mutabakat: katkı toplamı fonun gerçek getirisini tutturmalı
        fark = kdf["katki"].sum() - r["getiri"]
        st.caption(f"Katkı toplamı %{kdf['katki'].sum():.2f} — "
                   f"fonun gerçek getirisi %{r['getiri']:.2f} — "
                   f"fark **{fark:+.2f}** puan")
        if veri_yok:
            st.caption(f"Yetersiz veri: {', '.join(veri_yok)}")

        ilk_son = pd.concat([kdf.head(8), kdf.tail(8)])
        fig2 = px.bar(ilk_son, x="katki", y="ticker", orientation="h",
                      color="katki", color_continuous_midpoint=0,
                      color_continuous_scale=["#c0392b", "#eeeeee", "#27ae60"])
        fig2.update_layout(height=500, yaxis=dict(autorange="reversed"),
                           showlegend=False, coloraxis_showscale=False)
        st.plotly_chart(fig2, use_container_width=True)

        # --- Kazananlar / kaybedenler ---
        if len(kdf) >= 2:
            kk1, kk2 = st.columns(2)
            kaz = kdf.head(5)
            kayb = kdf.tail(5).iloc[::-1]
            with kk1:
                st.caption(f"🟢 {donem_adi} en çok TAŞIYAN 5 hisse")
                st.dataframe(
                    kaz[["ticker", "getiri", "katki"]]
                    .rename(columns={"ticker": "Hisse", "getiri": "Getiri %",
                                     "katki": "Katkı puan"}).round(1),
                    hide_index=True, use_container_width=True)
            with kk2:
                st.caption(f"🔴 {donem_adi} en çok BATIRAN 5 hisse")
                st.dataframe(
                    kayb[["ticker", "getiri", "katki"]]
                    .rename(columns={"ticker": "Hisse", "getiri": "Getiri %",
                                     "katki": "Katkı puan"}).round(1),
                    hide_index=True, use_container_width=True)

        # --- Endeks karşılaştırması (S&P 500 + Nasdaq) ---
        st.subheader("Endekslere karşı fiyat")
        st.caption(f"{donem_adi} başından itibaren yüzde getiri. USD bazlı.")
        fig3 = go.Figure()
        for t, ad, renk in [(fon, fon, "#1f77b4"),
                            (GOSTERGE, "S&P 500", "#e67e22"),
                            (NASDAQ, "Nasdaq", "#999999")]:
            if t not in fiyat:
                continue
            s = fiyat[t].iloc[-gun:].dropna()
            if len(s) < 2:
                continue
            fig3.add_trace(go.Scatter(
                x=s.index, y=(s / s.iloc[0] - 1) * 100, name=ad,
                line=dict(color=renk, width=2)))
        fig3.update_layout(height=400, yaxis_title=f"{donem_adi} başından (%)",
                           hovermode="x unified", margin=dict(t=10))
        st.plotly_chart(fig3, use_container_width=True)

        # --- Yıllık getiriler ---
        st.subheader("Yıllık getiriler")
        st.caption("Takvim yılı içi getiri (USD). Son yıl bu yılın başından "
                   "bugüne (YTD).")
        yg = yillik_getiriler(fiyat[fon])
        if len(yg) >= 2:
            bugun_yil = pd.Timestamp.today().year
            etiketler = [f"{int(yil)} (YTD)" if int(yil) == bugun_yil
                         else str(int(yil)) for yil in yg.index]
            figy = px.bar(x=etiketler, y=yg.values,
                          labels={"x": "", "y": "Getiri (%)"},
                          text=[f"%{v:.0f}" for v in yg.values])
            figy.update_traces(
                marker_color=["#27ae60" if v >= 0 else "#c0392b"
                              for v in yg.values],
                textposition="outside")
            figy.update_layout(height=340, margin=dict(t=10))
            st.plotly_chart(figy, use_container_width=True)

        # --- Korelasyon: neyle birlikte hareket ediyor ---
        st.subheader("Neyle birlikte hareket ediyor?")
        st.caption("Günlük getiri korelasyonu (seçili dönem). 1'e yakın = "
                   "birlikte hareket eder, 0 = ilgisiz, negatif = ters. "
                   "Bitcoin, Nasdaq ve S&P 500 ile.")
        kor_fiyat = fiyat_yukle((fon, BITCOIN, NASDAQ, GOSTERGE))
        kor = korelasyon(kor_fiyat, fon, KORELASYON_VARLIK, gun)
        if not kor.empty:
            ad_map = {fon: fon, BITCOIN: "Bitcoin", NASDAQ: "Nasdaq",
                      GOSTERGE: "S&P 500"}
            kor = kor.rename(index=ad_map, columns=ad_map)
            figk = px.imshow(kor, text_auto=".2f", zmin=-1, zmax=1,
                             color_continuous_scale=["#c0392b", "#ffffff",
                                                     "#1f77b4"],
                             labels=dict(color="Korelasyon"))
            figk.update_layout(height=360, margin=dict(t=10),
                               coloraxis_showscale=False)
            st.plotly_chart(figk, use_container_width=True)
        else:
            st.info("Korelasyon için yeterli veri yok.")

        # --- Alternatif yatırımlara karşı (TL / USD) ---
        st.divider()
        st.subheader("Alternatif yatırımlara karşı")
        para = st.radio("Para birimi", ["TL bazlı", "USD bazlı"],
                        horizontal=True, key="alt_para")
        para_kodu = "TL" if para.startswith("TL") else "USD"

        alt_fiyat = alt_fiyat_yukle()
        # fon fiyatını alt varlıklarla aynı çerçevede birleştir
        alt_cerceve = alt_fiyat.join(fiyat[[fon]], how="outer")
        alt_df = alternatif_getiriler(
            alt_cerceve, fon, para=para_kodu,
            faiz_yillik=faiz_yillik / 100, donemler=DONEMLER_ALT)

        if para_kodu == "TL":
            st.caption(f"Lira bazlı: USD varlıklar USD/TRY ile çevrildi. "
                       f"'Faiz' = yıllık %{faiz_yillik:.0f} TL mevduat varsayımı "
                       "(piyasa verisi değil).")
        else:
            st.caption("USD (dolar) bazlı: 'dolar' baz para olduğu için grafikte "
                       "yok, 'euro' = EUR/USD.")

        # TL modunda fonun getirisini ayrıştır: hisse (USD) + kur = TL
        if para_kodu == "TL":
            df_a = alt_cerceve.loc[alt_cerceve[fon].notna()].ffill()
            n = min(252, len(df_a))
            if n >= 2:
                usd_f = (df_a[fon].iloc[-1] / df_a[fon].iloc[-n] - 1) * 100
                kur = (df_a["TRY=X"].iloc[-1] / df_a["TRY=X"].iloc[-n] - 1) * 100
                tl_f = ((1 + usd_f / 100) * (1 + kur / 100) - 1) * 100
                st.caption(f"**{fon} son ~1 yıl — TL getirisi nereden geliyor?**")
                a1, a2, a3 = st.columns(3)
                a1.metric("Hisse getirisi (USD)", f"%{usd_f:.1f}",
                          help="Fonun dolar cinsinden değer artışı.")
                a2.metric("Kur katkısı (USD/TRY)", f"%{kur:.1f}",
                          help="Liranın dolara karşı değer kaybı; dolar varlığını "
                               "TL cinsinden değerli kılar.")
                a3.metric(f"{fon} TL bazlı = ", f"%{tl_f:.1f}",
                          help="Hisse × kur birleşik. Toplamdan biraz fazla, çünkü "
                               "kur kazancı hissenin kârının üstüne de biner.")

        with st.expander("💡 TL bazlı ve USD bazlı neden farklı?"):
            st.markdown(
                "Fonlar ve altın USD cinsinden fiyatlanır. **TL bazlı** getiri, "
                "USD getirinin üstüne **liranın dolara karşı değer kaybını** ekler:\n\n"
                "`TL getiri ≈ (1 + USD getiri) × (1 + USD/TRY artışı) − 1`\n\n"
                "Yani **hem hisseden hem dolardan** kazanırsın ve TL getirisi USD'den "
                "**daha çok** çıkar (lira değer kaybettiği sürece). Toplamdan biraz "
                "fazla olması, kur kazancının hissenin kârının üstüne de binmesindendir.")

        # dönem sırası korunur, fonun kendi barı koyu renkte vurgulanır
        alt_df["donem"] = pd.Categorical(alt_df["donem"],
                                         list(DONEMLER_ALT), ordered=True)
        renk_haritasi = dict(ALT_RENK)
        renk_haritasi[fon] = "#1f77b4"
        sira_varlik = [fon] + [v for v in ALT_RENK if v in alt_df["varlik"].values]
        figa = px.bar(alt_df.sort_values("donem"), x="donem", y="getiri",
                      color="varlik", barmode="group",
                      category_orders={"varlik": sira_varlik},
                      color_discrete_map=renk_haritasi,
                      labels={"donem": "", "getiri": "Getiri (%)", "varlik": ""})
        figa.update_layout(height=430, margin=dict(t=10),
                           legend=dict(orientation="h", y=1.12))
        st.plotly_chart(figa, use_container_width=True)


# =====================================================================
# Karşılaştırma
# =====================================================================
with karsilastirma_sekme:
    hepsi = tum_holdings(tema)
    fon_fiyat = fiyat_yukle(tuple(hepsi) + (GOSTERGE, RISKSIZ))
    risksiz = risksiz_gunluk_oran(fon_fiyat[RISKSIZ].iloc[-gun:])

    st.title(f"{tema} — {donem_adi}")
    snapshot_notu(hepsi)

    # --- Yan yana tablo ---
    st.subheader("Fonlar yan yana")
    satirlar = {}
    for f, hh in hepsi.items():
        y_f = yogunlasma(hh)
        r_f = risk_metrikleri(fon_fiyat[f].iloc[-gun:], risksiz)
        satirlar[f] = {
            "Gider %": FON_BILGI[f][2] if f in FON_BILGI else None,
            "Hisse sayısı": y_f["hisse_sayisi"],
            "Etkin hisse": round(y_f["etkin_hisse"], 1),
            "En büyük %": round(y_f["en_buyuk"], 1),
            "İlk 3 %": round(y_f["top_3"], 1),
            "İlk 10 %": round(y_f["top_10"], 1),
            "HHI": round(y_f["hhi"]),
            "Getiri %": round(r_f["getiri"], 1),
            "Volatilite %": round(r_f["volatilite"], 1),
            "Sharpe": round(r_f["sharpe"], 2),
            "Maks. düşüş %": round(r_f["max_dusus"], 1),
        }
    st.dataframe(pd.DataFrame(satirlar), use_container_width=True)

    with st.expander("ℹ️ Satırlar ne anlama geliyor?"):
        st.markdown(
            "- **Gider %** — fonun yıllık işletme gideri (expense ratio). "
            "Düşük olması iyidir; aynı temada ucuz fon uzun vadede avantajlı.\n"
            "- **Hisse sayısı** — fonun kaç farklı hisse tuttuğu.\n"
            "- **Etkin hisse** — ağırlıklar dikkate alınınca 'gerçekte' kaç "
            "hisseye yayıldığı. Sayı ne kadar yüksekse o kadar dağıtılmış. "
            "(Örn. 25 hisse tutup birine %90 verirse etkin hisse ~1'dir.)\n"
            "- **En büyük %** — en büyük tek pozisyonun ağırlığı.\n"
            "- **İlk 3 % / İlk 10 %** — en büyük 3 (ve 10) hissenin toplam "
            "ağırlığı. Yüksekse fon birkaç hisseye yoğunlaşmış demektir.\n"
            "- **HHI** — yoğunlaşma endeksi (ağırlıkların karelerinin toplamı). "
            "Yükseldikçe fon daha az hisseye yığılmış olur; 10000 = tek hisse.\n"
            "- **Getiri %** — seçili dönemdeki fiyat getirisi (USD).\n"
            "- **Volatilite %** — yıllıklandırılmış oynaklık; risk ölçüsü, "
            "yüksekse fiyat daha çok zıplıyor.\n"
            "- **Sharpe** — risk başına getiri (getiri ÷ oynaklık, faiz "
            "düşülerek). Yüksek/pozitif iyi, negatif = riske değmemiş.\n"
            "- **Maks. düşüş %** — dönem içinde zirveden en dip noktaya "
            "yaşanan en büyük kayıp.")

    # genç fonlar: seçilen dönem kadar geçmişi olmayanları belirt
    genc = [f for f in hepsi if int(fon_fiyat[f].notna().sum()) < gun * 0.95]
    if genc:
        st.caption(f"⚠️ {', '.join(genc)} için {donem_adi} kadar geçmiş yok; "
                   "bu fonların getiri/risk değerleri daha kısa süreye aittir.")

    # --- Normalize performans (kullanıcı seçimli) ---
    st.subheader("Göreli performans")
    st.caption("Karşılaştırmak istediklerini seç — grafik sadece onları çizer.")

    gc1, gc2 = st.columns([3, 2])
    fon_secili = gc1.multiselect(
        "Fonlar", list(hepsi),
        default=[fon] if fon in hepsi else list(hepsi)[:2],
        key="gp_fon")
    gosterge_secili = gc2.multiselect(
        "Karşılaştırma", ["S&P 500", "Nasdaq", "Bitcoin"],
        default=["S&P 500"], key="gp_gosterge")

    if not fon_secili and not gosterge_secili:
        st.info("En az bir fon ya da karşılaştırma seç.")
    else:
        # pencere fonların işlem günleri (BTC hafta sonları hariç)
        pencere_idx = fon_fiyat.iloc[-gun:].index
        gosterge_map = {"S&P 500": GOSTERGE, "Nasdaq": NASDAQ, "Bitcoin": BITCOIN}
        gosterge_renk = {"S&P 500": "#999999", "Nasdaq": "#e67e22",
                         "Bitcoin": "#f1c40f"}
        bench = fiyat_yukle(tuple(gosterge_map[g] for g in gosterge_secili)) \
            if gosterge_secili else None

        fig4 = go.Figure()
        for t in fon_secili:
            s = fon_fiyat[t].reindex(pencere_idx).dropna()
            if len(s) < 2:
                continue
            fig4.add_trace(go.Scatter(
                x=s.index, y=(s / s.iloc[0] - 1) * 100, name=t,
                line=dict(width=2.5)))
        for g in gosterge_secili:
            s = bench[gosterge_map[g]].reindex(pencere_idx).ffill().dropna()
            if len(s) < 2:
                continue
            fig4.add_trace(go.Scatter(
                x=s.index, y=(s / s.iloc[0] - 1) * 100, name=g,
                line=dict(width=2, dash="dot", color=gosterge_renk[g])))
        fig4.update_layout(height=430, yaxis_title=f"{donem_adi} başından (%)",
                           hovermode="x unified", margin=dict(t=10),
                           legend=dict(orientation="h", y=1.12))
        st.plotly_chart(fig4, use_container_width=True)

    # --- Örtüşme ---
    st.subheader("Portföy örtüşmesi")
    st.caption("Ortak hisselerde min(ağırlık) toplamı. "
               "%100 birebir aynı portföy, %0 hiç ortak hisse yok.")
    ort = ortusme(hepsi)
    fig5 = px.imshow(ort, text_auto=".1f", zmin=0, zmax=100,
                     color_continuous_scale=["#ffffff", "#c0392b"],
                     labels=dict(color="Örtüşme %"))
    fig5.update_layout(height=380, margin=dict(t=10),
                       coloraxis_showscale=False)
    st.plotly_chart(fig5, use_container_width=True)

    # --- Ortak hisseler ---
    st.subheader("Hepsinde bulunan hisseler")
    ortak = ortak_hisseler(hepsi)
    st.caption(f"{len(ortak)} hisse {len(hepsi)} fonun hepsinde var. "
               "Ağırlık farkı fonların nasıl ayrıştığını gösterir.")
    st.dataframe(ortak.round(2), use_container_width=True)


# =====================================================================
# Hisse bazlı — tüm temalardaki fonlar
# =====================================================================
with hisse_sekme:
    st.title("Hisse bazlı sıralama")

    hepsi_fon = her_fon()
    matris = ortak_hisseler(hepsi_fon, en_az=1)

    st.caption(f"{len(matris)} hisse, {len(hepsi_fon)} fon "
               f"({', '.join(hepsi_fon)}). Tema fark etmeksizin hepsi.")
    snapshot_notu(hepsi_fon)

    harita = sektor_yukle()

    # --- tek hisse: hangi fon en çok tutuyor ---
    st.subheader("Bir hisseyi en çok hangi fon tutuyor?")
    st.caption("Çok fazla hisse var — sektörle daralt ya da 'birden fazla "
               "fonda olanlar'ı işaretli bırak.")

    kac_fon = matris.notna().sum(axis=1)
    f1, f2 = st.columns([2, 1])
    sektor_secenek = ["Tüm sektörler"]
    if harita:
        sektor_secenek += sorted(set(harita.get(t, "Diğer")
                                     for t in matris.index))
    sec_sektor = f1.selectbox("Sektör filtresi", sektor_secenek)
    sadece_cok = f2.checkbox("Birden fazla fonda", value=True)

    adaylar = list(matris.index)
    if sec_sektor != "Tüm sektörler" and harita:
        adaylar = [t for t in adaylar if harita.get(t, "Diğer") == sec_sektor]
    if sadece_cok:
        adaylar = [t for t in adaylar if kac_fon[t] >= 2]
    # önemliler üstte: önce fon sayısı, sonra toplam ağırlık
    adaylar.sort(key=lambda t: (-int(kac_fon[t]), -float(matris.loc[t].sum())))
    etiket = {f"{t}  ·  {int(kac_fon[t])} fonda": t for t in adaylar}

    if not etiket:
        st.info("Bu filtreyle hisse kalmadı.")
    else:
        vk = next((k for k, v in etiket.items() if v == "NVDA"),
                  list(etiket)[0])
        sec_et = st.selectbox(f"Hisse ({len(etiket)} seçenek)",
                              list(etiket), index=list(etiket).index(vk))
        secili = etiket[sec_et]

        sira = hisse_siralamasi(hepsi_fon, secili)
        en = sira.index[0]
        st.metric(f"{secili} — en çok tutan fon",
                  f"{en}  %{sira.iloc[0]:.2f}")
        figh = px.bar(x=sira.values, y=sira.index, orientation="h",
                      labels={"x": "Ağırlık (%)", "y": ""},
                      text=[f"%{v:.2f}" for v in sira.values])
        figh.update_traces(marker_color="#1f77b4", textposition="outside")
        figh.update_layout(height=90 + 45 * len(sira),
                           yaxis=dict(autorange="reversed"),
                           margin=dict(t=10, r=60))
        st.plotly_chart(figh, use_container_width=True)

    st.divider()

    # --- Fon × Sektör dağılımı ---
    if not harita:
        st.info("Sektör haritası yok — `python3 sektorler.py` ile üretilebilir.")
    else:
        st.subheader("Fonların sektör dağılımı")
        st.caption("Her fon ağırlığının sektörlere dağılımı (%). "
                   "Fonların karakterini gösterir: yarı iletken mi, "
                   "yazılım mı, havacılık mı ağırlıklı.")

        fs = fon_sektor_agirliklari(hepsi_fon, harita)   # sektör × fon
        fs = fs.loc[fs.sum(axis=1).sort_values(ascending=False).index]

        figs = px.imshow(fs, text_auto=".0f", aspect="auto",
                         color_continuous_scale=["#ffffff", "#1f77b4"],
                         labels=dict(color="Ağırlık %"))
        figs.update_layout(height=60 + 40 * len(fs), margin=dict(t=10),
                           coloraxis_showscale=False, xaxis_side="top")
        st.plotly_chart(figs, use_container_width=True)

        st.divider()

        # --- Sektör seçici: o sektördeki hisseler ---
        st.subheader("Sektöre göre hisseler")
        sektor_sec = st.selectbox("Sektör", list(fs.index))

        # long tablo: (ticker, fon, ağırlık) sadece seçili sektör
        kayit = []
        for f, hh in hepsi_fon.items():
            for t, w in zip(hh["ticker"], hh["weight"]):
                if harita.get(t, "Diğer") == sektor_sec:
                    kayit.append({"ticker": t, "fon": f, "weight": w})
        if not kayit:
            st.info("Bu sektörde hisse yok.")
        else:
            uzun = pd.DataFrame(kayit)
            piv = (uzun.pivot_table(index="ticker", columns="fon",
                                    values="weight", aggfunc="sum")
                       .fillna(0.0))
            piv = piv.loc[piv.sum(axis=1).sort_values(ascending=False).index]
            st.caption(f"{sektor_sec}: {len(piv)} hisse. "
                       "Değerler o fondaki ağırlık (%).")
            st.dataframe(piv.round(2), use_container_width=True,
                         height=min(420, 60 + 36 * len(piv)))


# =====================================================================
# Portföy simülatörü — geçmiş "ne olurdu" simülasyonu
# =====================================================================
with portfoy_sekme:
    st.title("Portföy simülatörü")
    st.caption("Farklı varlıkları karıştırıp geçmişte ne getireceğini gör. "
               "Slider'larla dağılımı ayarla.")
    st.info("📌 Bu bir **geçmiş simülasyondur, yatırım tavsiyesi değildir.** "
            "Geçmiş getiri geleceği garanti etmez.", icon="⚠️")

    ust1, ust2, ust3 = st.columns(3)
    p_para = ust1.radio("Para birimi", ["TL bazlı", "USD bazlı"],
                        horizontal=True, key="p_para")
    p_kodu = "TL" if p_para.startswith("TL") else "USD"
    p_fon = ust2.selectbox("Fon", [f for t in FONLAR for f in FONLAR[t]],
                           key="p_fon")
    p_donem = ust3.selectbox("Dönem", list(DONEMLER.keys()), index=3,
                             key="p_donem")
    p_gun = DONEMLER[p_donem]
    p_tutar = st.number_input(
        f"Başlangıç tutarı ({'TL' if p_kodu=='TL' else 'USD'})",
        min_value=100, value=10000, step=1000, key="p_tutar")

    # varlık slider'ları
    st.caption("Dağılım (%) — otomatik %100'e ölçeklenir:")
    varliklar = [p_fon, "Altın", "Gümüş"]
    if p_kodu == "TL":
        varliklar.append("Dolar")
    varliklar += ["Euro", "Faiz"]

    kolonlar = st.columns(len(varliklar))
    agirliklar = {}
    varsayilan = {p_fon: 40, "Altın": 20, "Gümüş": 0, "Dolar": 15,
                  "Euro": 0, "Faiz": 25}
    for k, v in zip(kolonlar, varliklar):
        agirliklar[v] = k.slider(v, 0, 100, varsayilan.get(v, 0), 5,
                                 key=f"p_slider_{v}")

    toplam = sum(agirliklar.values())
    if toplam == 0:
        st.warning("En az bir varlığa ağırlık ver.")
    else:
        st.caption(f"Toplam: %{toplam} → %100'e ölçeklendi: " +
                   ", ".join(f"{k} %{v/toplam*100:.0f}"
                             for k, v in agirliklar.items() if v > 0))

        alt = alt_fiyat_yukle()
        fpx = fiyat_yukle((p_fon, GOSTERGE, RISKSIZ))
        cerceve = alt.join(fpx[[p_fon]], how="outer")

        portfoy, bilesenler = portfoy_serisi(
            cerceve, p_fon, agirliklar, para=p_kodu,
            faiz_yillik=faiz_yillik / 100, gun=p_gun, baslangic=p_tutar)

        if portfoy.empty:
            st.info("Bu dönem/para birimi için veri yetersiz.")
        else:
            son = portfoy.iloc[-1]
            getiri = (son / p_tutar - 1) * 100
            gercek_yil = len(portfoy) / 252
            m1, m2, m3 = st.columns(3)
            m1.metric(f"{p_tutar:,.0f} → bugün", f"{son:,.0f}")
            m2.metric("Getiri", f"%{getiri:.1f}")
            m3.metric("Süre", f"{gercek_yil:.1f} yıl")
            if gercek_yil < p_gun / 252 * 0.95:
                st.caption(f"⚠️ {p_fon} bu kadar eski değil; "
                           f"simülasyon {gercek_yil:.1f} yılla sınırlı.")

            # portföy + bileşenler büyüme çizgisi
            fig = go.Figure()
            fig.add_trace(go.Scatter(
                x=portfoy.index, y=portfoy, name="PORTFÖY",
                line=dict(color="#1f77b4", width=3.5)))
            renk = {p_fon: "#e67e22", "Altın": "#f1c40f", "Gümüş": "#95a5a6",
                    "Dolar": "#27ae60", "Euro": "#8e44ad", "Faiz": "#c0392b"}
            for k in bilesenler.columns:
                fig.add_trace(go.Scatter(
                    x=bilesenler.index, y=bilesenler[k], name=k,
                    line=dict(color=renk.get(k), width=1, dash="dot"),
                    opacity=0.6))
            fig.update_layout(height=430, hovermode="x unified",
                              yaxis_title=f"Değer ({'TL' if p_kodu=='TL' else 'USD'})",
                              margin=dict(t=10),
                              legend=dict(orientation="h", y=1.1))
            st.plotly_chart(fig, use_container_width=True)
            st.caption("Kalın çizgi: karma portföy. Noktalı çizgiler: her "
                       "varlık tek başına aynı tutarla ne yapardı.")
