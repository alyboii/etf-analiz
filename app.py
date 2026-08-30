import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
import yfinance as yf

from parsers import parse_vaneck, parse_ishares, parse_spdr
from metrikler import (donem_getirisi, yogunlasma, katki,
                       risk_metrikleri, drawdown_serisi)

st.set_page_config(page_title="ETF Analiz", layout="wide")

FONLAR = {
    "Yarı iletken": {
        "SMH":  (parse_vaneck,  "data/raw/SMH_asof_20260827.xlsx"),
        "SOXX": (parse_ishares, "data/raw/SOXX_holdings.csv"),
        "XSD":  (parse_spdr,    "data/raw/holdings-daily-us-en-xsd.xlsx"),
    },
    "Uzay": {},
}

DONEMLER = {"1 ay": 21, "3 ay": 63, "6 ay": 126, "1 yıl": 252}


@st.cache_data
def holdings_yukle(fon, tema):
    parser, yol = FONLAR[tema][fon]
    return parser(yol, fon)


@st.cache_data
def fiyat_yukle(tickerlar):
    df = yf.download(list(tickerlar), start="2025-08-01",
                     auto_adjust=True, progress=False)["Close"]
    return df.dropna(how="all")


# --- Kenar çubuğu ---
st.sidebar.title("ETF Analiz")
tema = st.sidebar.radio("Tema", [t for t in FONLAR if FONLAR[t]])
fon = st.sidebar.radio("Fon", list(FONLAR[tema].keys()))
donem_adi = st.sidebar.selectbox("Dönem", list(DONEMLER.keys()), index=1)
gun = DONEMLER[donem_adi]

st.sidebar.caption("Tüm getiriler USD bazlıdır.")

# --- Veri ---
h = holdings_yukle(fon, tema)
fiyat = fiyat_yukle(tuple(h["ticker"]) + (fon, "^GSPC"))
getiri = donem_getirisi(fiyat, gun)

# --- Başlık ---
st.title(f"{fon} — {donem_adi}")
st.caption(f"Holdings tarihi: {h['date'].iloc[0].date()}")

# --- Kimlik kartı ---
y = yogunlasma(h)
r = risk_metrikleri(fiyat[fon].iloc[-gun:])

k1, k2, k3, k4, k5 = st.columns(5)
k1.metric("Hisse sayısı", y["hisse_sayisi"])
k2.metric("Etkin hisse", f"{y['etkin_hisse']:.1f}")
k3.metric("En büyük pozisyon", f"%{y['en_buyuk']:.1f}")
k4.metric(f"{donem_adi} getiri", f"%{r['getiri']:.1f}")
k5.metric("Maks. düşüş", f"%{r['max_dusus']:.1f}")

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
kdf, veri_yok = katki(h, getiri)
st.caption("Katkı = güncel ağırlık × dönem getirisi (yaklaşık hesap).")
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
for t, ad, renk in [(fon, fon, "#1f77b4"), ("^GSPC", "S&P 500", "#999999")]:
    dd = drawdown_serisi(fiyat[t].iloc[-gun:])
    fig3.add_trace(go.Scatter(x=dd.index, y=dd, name=ad,
                              line=dict(color=renk, width=2)))
fig3.update_layout(height=400, yaxis_title="Zirveye göre (%)",
                   hovermode="x unified", margin=dict(t=10))
st.plotly_chart(fig3, use_container_width=True)
