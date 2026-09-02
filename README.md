# ETF Analiz Dashboard

Yarı iletken, uzay ve yapay zeka temalı ETF'leri karşılaştıran, Türkçe bir
Streamlit paneli. Fon holdings'lerini ayrıştırır, getiriye katkıyı hesaplar,
fonları alternatif yatırımlarla (altın, gümüş, dolar, euro, faiz) TL/USD bazlı
karşılaştırır ve geçmişe dönük portföy simülasyonu yapar.

## Temalar ve fonlar (11 + DXYZ)

| Tema | Fonlar |
|---|---|
| Yarı iletken | SMH, SOXX, XSD, SMHX, SOXQ, PSI |
| Uzay | ROKT, NASA |
| Yapay Zeka | IGV, AIQ, CHAT |
| (ayrı sekme) | DXYZ — Destiny Tech100 (özel şirket maruziyeti: Anthropic, SpaceX, OpenAI) |

## Sekmeler

- **Fon detayı** — yoğunlaşma + risk metrikleri, treemap, getiriye katkı
  (dönem başı / güncel ağırlık), S&P 500 + Nasdaq karşılaştırması, alternatif
  yatırımlara karşı (TL/USD).
- **Karşılaştırma** — fonlar yan yana, göreli performans, portföy örtüşmesi,
  ortak hisseler.
- **Hisse bazlı** — bir hisseyi en çok tutan fonlar; fon × sektör ısı haritası;
  sektöre göre hisseler.
- **Portföy simülatörü** — varlık dağılımı slider'larıyla geçmiş "ne olurdu"
  simülasyonu. *Yatırım tavsiyesi değildir.*
- **DXYZ** — ticker'sız özel şirket pozisyonları (SEC N-PORT).

## Çalıştırma

```bash
pip install -r requirements.txt
streamlit run app.py
```

## Veriyi güncelleme

Otomatik çekilebilenler (iShares, SPDR):

```bash
python3 guncelle.py            # SOXX, IGV, XSD, ROKT'u en güncel güne çeker
python3 guncelle.py --sektor   # ayrıca sektör haritasını yeniler
python3 guncelle.py --dogrula  # ayrıca doğrulama çalıştırır
```

Elle indirilecekler (siteleri oturumlu/JS-render) — `data/raw/` altındaki
mevcut dosya adlarıyla değiştir: VanEck (SMH, SMHX), Invesco (SOXQ, PSI),
Global X (AIQ), Roundhill (CHAT), Tema (NASA). Linkler `guncelle.py`
çıktısında listelenir.

## Doğrulama

```bash
python3 dogrula.py           # ağırlık≈100, shares×fiyat≈market_value, ticker eşleşme
python3 dogrula.py --hizli   # isim çapraz kontrolünü atla (hızlı)
```

## Yayına alma (Streamlit Community Cloud)

1. Repo GitHub'da: https://github.com/alyboii/etf-analiz
2. https://share.streamlit.io → "New app" → repo + branch `main` + `app.py`
3. Deploy. İlk açılışta fiyat verisi yfinance'ten çekilir (~30-60 sn),
   sonrası önbellekten hızlı gelir.

## Veri kaynakları

- Holdings: fon sağlayıcıları (iShares/BlackRock, SPDR/SSGA, VanEck, Invesco,
  Global X, Roundhill, Tema) ve SEC N-PORT (DXYZ, geçmiş holdings).
- Fiyatlar: yfinance. Yabancı borsalar Bloomberg → yfinance sembolüne çevrilir.
- Geçmiş holdings: `gecmis.py` (SOXX günlük 5 yıl, diğerleri çeyreklik N-PORT).

## Sınırlar

- Fon metrikleri (getiri, Sharpe, drawdown) USD bazlıdır; "alternatif" ve
  "portföy" bölümlerinde TL/USD seçilebilir.
- "Faiz" TL modunda ayarlanabilir bir varsayımdır (piyasa verisi değil).
- Fonlar farklı günlerden olabilir; karşılaştırma sekmesi tarih tutarsızlığında
  uyarır.
- DXYZ pozisyonları özel şirket (ticker yok) — getiri/katkı hesaplanamaz.
- **Bu araç bilgilendirme amaçlıdır, yatırım tavsiyesi değildir.**

---
🤖 Generated with [Claude Code](https://claude.com/claude-code)
