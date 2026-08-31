from pathlib import Path

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
import yfinance as yf

from parsers import parse_vaneck, parse_ishares, parse_spdr
from metrikler import (donem_getirisi, yogunlasma, katki,
                       risk_metrikleri, drawdown_serisi,
                       risksiz_gunluk_oran, ortusme, ortak_hisseler,
                       katki_donem_basi, hisse_siralamasi)

st.set_page_config(page_title="ETF Analiz", layout="wide")

FONLAR = {
    "Yarı iletken": {
        "SMH":  (parse_vaneck,  "data/raw/SMH_asof_20260827.xlsx"),
        "SOXX": (parse_ishares, "data/raw/SOXX_holdings.csv"),
        "XSD":  (parse_spdr,    "data/raw/holdings-daily-us-en-xsd.xlsx"),
    },
    "Uzay": {
        "ROKT": (parse_spdr, "data/raw/holdings-daily-us-en-rokt.xlsx"),
    },
}

DONEMLER = {"1 ay": 21, "3 ay": 63, "6 ay": 126, "1 yıl": 252,
            "3 yıl": 756, "5 yıl": 1260}

RISKSIZ = "BIL"      # kısa vadeli hazine ETF'i, Sharpe'ın risksiz oranı
GOSTERGE = "^GSPC"   # S&P 500


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
    df = yf.download(list(tickerlar), start="2019-01-01",
                     auto_adjust=True, progress=False)["Close"]
    return df.dropna(how="all")


@st.cache_data
def gecmis_yukle():
    """Geçmiş holdings (gecmis.py ile toplanır). Yoksa None."""
    yol = Path("data/history/holdings.parquet")
    return pd.read_parquet(yol) if yol.exists() else None


# --- Kenar çubuğu ---
st.sidebar.title("ETF Analiz")
tema = st.sidebar.radio("Tema", [t for t in FONLAR if FONLAR[t]])
fon = st.sidebar.radio("Fon", list(FONLAR[tema].keys()))
donem_adi = st.sidebar.selectbox("Dönem", list(DONEMLER.keys()), index=1)
gun = DONEMLER[donem_adi]

st.sidebar.caption("Tüm getiriler USD bazlıdır.")
st.sidebar.caption(f"Sharpe'ta risksiz oran: {RISKSIZ}")

detay_sekme, karsilastirma_sekme, hisse_sekme, dxyz_sekme = st.tabs(
    ["Fon detayı", "Karşılaştırma", "Hisse bazlı", "DXYZ — özel şirketler"])


# =====================================================================
# Fon detayı
# =====================================================================
with detay_sekme:
    h = holdings_yukle(fon, tema)

    # geçmiş holdings'teki ticker'lar da lazım: portföyden çıkmış hisseler
    # olmadan dönem başı katkısı eksik hesaplanır
    gec_tum = gecmis_yukle()
    eski = ()
    if gec_tum is not None:
        eski = tuple(sorted(set(gec_tum[gec_tum["fund"] == fon]["ticker"])
                            - set(h["ticker"])))

    fiyat = fiyat_yukle(tuple(h["ticker"]) + eski + (fon, GOSTERGE, RISKSIZ))
    getiri = donem_getirisi(fiyat, gun)

    st.title(f"{fon} — {donem_adi}")
    st.caption(f"Holdings tarihi: {h['date'].iloc[0].date()}")

    # --- Kimlik kartı ---
    y = yogunlasma(h)
    risksiz = risksiz_gunluk_oran(fiyat[RISKSIZ].iloc[-gun:])
    r = risk_metrikleri(fiyat[fon].iloc[-gun:], risksiz)

    st.caption("Portföy yapısı")
    k1, k2, k3, k4, k5 = st.columns(5)
    k1.metric("Hisse sayısı", y["hisse_sayisi"])
    k2.metric("Etkin hisse", f"{y['etkin_hisse']:.1f}")
    k3.metric("En büyük pozisyon", f"%{y['en_buyuk']:.1f}")
    k4.metric("İlk 10 ağırlığı", f"%{y['top_10']:.1f}")
    k5.metric("HHI", f"{y['hhi']:.0f}")

    st.caption(f"Risk ve getiri — {donem_adi}")
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Getiri", f"%{r['getiri']:.1f}")
    m2.metric("Volatilite (yıllık)", f"%{r['volatilite']:.1f}")
    m3.metric("Sharpe", f"{r['sharpe']:.2f}")
    m4.metric("Maks. düşüş", f"%{r['max_dusus']:.1f}")

    st.divider()

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

    # --- Drawdown ---
    st.subheader("Zirveden düşüş")
    fig3 = go.Figure()
    for t, ad, renk in [(fon, fon, "#1f77b4"), (GOSTERGE, "S&P 500", "#999999")]:
        dd = drawdown_serisi(fiyat[t].iloc[-gun:])
        fig3.add_trace(go.Scatter(x=dd.index, y=dd, name=ad,
                                  line=dict(color=renk, width=2)))
    fig3.update_layout(height=400, yaxis_title="Zirveye göre (%)",
                       hovermode="x unified", margin=dict(t=10))
    st.plotly_chart(fig3, use_container_width=True)


# =====================================================================
# Karşılaştırma
# =====================================================================
with karsilastirma_sekme:
    hepsi = tum_holdings(tema)
    fon_fiyat = fiyat_yukle(tuple(hepsi) + (GOSTERGE, RISKSIZ))
    risksiz = risksiz_gunluk_oran(fon_fiyat[RISKSIZ].iloc[-gun:])

    st.title(f"{tema} — {donem_adi}")

    # --- Yan yana tablo ---
    st.subheader("Fonlar yan yana")
    satirlar = {}
    for f, hh in hepsi.items():
        y_f = yogunlasma(hh)
        r_f = risk_metrikleri(fon_fiyat[f].iloc[-gun:], risksiz)
        satirlar[f] = {
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

    # --- Normalize performans ---
    st.subheader("Göreli performans")
    pencere = fon_fiyat.iloc[-gun:]
    fig4 = go.Figure()
    for t in list(hepsi) + [GOSTERGE]:
        s = pencere[t].dropna()
        fig4.add_trace(go.Scatter(
            x=s.index, y=(s / s.iloc[0] - 1) * 100,
            name="S&P 500" if t == GOSTERGE else t,
            line=dict(width=2, dash="dot" if t == GOSTERGE else "solid",
                      color="#999999" if t == GOSTERGE else None),
        ))
    fig4.update_layout(height=400, yaxis_title=f"{donem_adi} başından (%)",
                       hovermode="x unified", margin=dict(t=10))
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
    st.caption(f"{len(ortak)} hisse üç fonda da var. "
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

    # --- tek hisse: hangi fon en çok tutuyor ---
    varsayilan = "NVDA" if "NVDA" in matris.index else matris.index[0]
    secili = st.selectbox("Hisse", list(matris.index),
                          index=list(matris.index).index(varsayilan))

    sira = hisse_siralamasi(hepsi_fon, secili)
    if sira.empty:
        st.info("Bu hisse hiçbir fonda yok.")
    else:
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

    # --- tüm matris ---
    st.subheader("Ağırlık matrisi")
    st.caption("Boş hücre: hisse o fonda yok. "
               "Toplam ağırlığa göre sıralı.")

    sirali = matris.loc[matris.sum(axis=1).sort_values(ascending=False).index]
    kac_fon = matris.notna().sum(axis=1)

    sadece_ortak = st.checkbox("Sadece birden fazla fonda olanlar", value=False)
    if sadece_ortak:
        sirali = sirali[kac_fon[sirali.index] > 1]

    st.dataframe(sirali.round(2), use_container_width=True, height=420)


# =====================================================================
# DXYZ — özel şirket maruziyeti
# =====================================================================
with dxyz_sekme:
    st.title("DXYZ — Destiny Tech100")

    sonuc = dxyz_yukle()
    if sonuc[0] == "hata":
        st.error(f"SEC verisi alınamadı: {sonuc[1]}")
    else:
        donem, dx = sonuc
        st.caption(f"SEC N-PORT dönemi: {donem} — veri üç aylık ve "
                   "~60 gün gecikmeli.")

        st.warning(
            "DXYZ bir ETF değil, kapalı uçlu fon. Pozisyonları özel "
            "şirketlere maruziyet veren SPV/LLC yapıları ve **ticker'ları "
            "yok** — bu yüzden hisse bazlı getiri, katkı ve risk metrikleri "
            "hesaplanamıyor. Aşağıda sadece isim ve ağırlık var.")

        nakit = dx[dx["nakit"]]["weight"].sum()
        d1, d2, d3 = st.columns(3)
        d1.metric("Pozisyon", len(dx))
        d2.metric("Nakit / para piyasası", f"%{nakit:.1f}")
        d3.metric("Özel şirket maruziyeti", f"%{100 - nakit:.1f}")

        # aynı şirket birden çok SPV'de olabiliyor (ör. SpaceX 3 kez);
        # isim temizliği gecmis._sirket_adi içinde yapılıyor
        birlesik = (dx[~dx["nakit"]].groupby("sirket")["weight"].sum()
                      .sort_values(ascending=False))

        st.subheader("Şirket bazında maruziyet")
        st.caption("Aynı şirkete birden fazla SPV üzerinden yatırım "
                   "yapılabiliyor; burada toplanmış hâli.")

        ust = birlesik.head(15)
        figd = px.bar(x=ust.values, y=ust.index, orientation="h",
                      labels={"x": "Fon içindeki ağırlık (%)", "y": ""},
                      text=[f"%{v:.2f}" for v in ust.values])
        figd.update_traces(
            marker_color=["#c0392b" if "Anthropic" in s else "#1f77b4"
                          for s in ust.index],
            textposition="outside")
        figd.update_layout(height=90 + 34 * len(ust),
                           yaxis=dict(autorange="reversed"),
                           margin=dict(t=10, r=70))
        st.plotly_chart(figd, use_container_width=True)

        with st.expander("Ham pozisyonlar (SPV isimleriyle)"):
            st.dataframe(
                dx[["name", "sirket", "weight", "varlik_tipi", "nakit"]]
                  .round(3),
                use_container_width=True)

        # --- fon fiyatı (DXYZ borsada işlem görüyor) ---
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
