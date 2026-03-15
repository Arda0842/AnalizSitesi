import streamlit as st
import yfinance as yf
import borsapy as bp
import ta
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import concurrent.futures
import psycopg2
import pandas as pd
import hashlib
from datetime import datetime, timedelta
import google.generativeai as genai

try:
    from tefas import Crawler
except ImportError:
    st.error("Lütfen terminalde 'pip install tefas-crawler' komutunu çalıştırın.")

# ==========================================
# 0. SUPABASE BAĞLANTISI
# ==========================================
def db_baglan():
    return psycopg2.connect(st.secrets["DATABASE_URL"])

def veri_tabani_kur():
    conn = db_baglan()
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users (username TEXT PRIMARY KEY, password TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS portfoy (username TEXT, sembol TEXT, maliyet REAL, lot REAL, piyasa TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS portfoy_gecmis (username TEXT, tarih TEXT, toplam_deger REAL)''')
    conn.commit()
    conn.close()

def sifre_hashle(sifre):
    return hashlib.sha256(str.encode(sifre)).hexdigest()

veri_tabani_kur()

# ==========================================
# 1. GİRİŞ VE KAYIT EKRANI
# ==========================================
if 'logged_in' not in st.session_state:
    st.session_state.logged_in = False
    st.session_state.user = None

if not st.session_state.logged_in:
    st.set_page_config(page_title="Arda Holding Giriş", layout="centered")
    st.title("🌍 Arda Holding Global Terminal")

    sekme_giris, sekme_kayit = st.tabs(["Giriş Yap", "Yeni Hesap Oluştur"])

    with sekme_giris:
        user = st.text_input("Kullanıcı Adı", key="login_user")
        pw   = st.text_input("Şifre", type='password', key="login_pw")
        if st.button("Sisteme Gir"):
            conn = db_baglan()
            c = conn.cursor()
            c.execute('SELECT * FROM users WHERE username=%s AND password=%s', (user, sifre_hashle(pw)))
            if c.fetchone():
                st.session_state.logged_in = True
                st.session_state.user = user
                st.rerun()
            else:
                st.error("Kullanıcı adı veya şifre hatalı!")
            conn.close()

    with sekme_kayit:
        new_user = st.text_input("Kullanıcı Adı Belirle", key="reg_user")
        new_pw   = st.text_input("Şifre Belirle", type='password', key="reg_pw")
        if st.button("Kayıt Ol"):
            conn = db_baglan()
            c = conn.cursor()
            try:
                c.execute('INSERT INTO users VALUES (%s,%s)', (new_user, sifre_hashle(new_pw)))
                conn.commit()
                st.success("Hesap oluşturuldu! Giriş yapabilirsiniz.")
            except:
                st.error("Bu kullanıcı adı zaten kullanımda!")
            conn.close()

# ==========================================
# 2. ANA TERMİNAL
# ==========================================
else:
    st.set_page_config(page_title="Arda Holding Terminal", page_icon="💼", layout="wide")

    # ── YARDIMCI FONKSİYONLAR ──────────────────────────────────
    def para_fmt(t):
        if abs(t) >= 1e9: return f"{t/1e9:.2f}B $"
        if abs(t) >= 1e6: return f"{t/1e6:.1f}M $"
        return f"{t:,.0f}"

    @st.cache_data(ttl=300)
    def borsapy_veri_cek(sembol):
        """borsapy ile teknik + ETF verisi çeker (5 dk cache)"""
        try:
            h    = bp.Ticker(sembol.replace(".IS",""))
            info = h.fast_info
            t    = h.technicals().latest

            fiyat      = float(getattr(info, "last_price",              0) or 0)
            market_cap = float(getattr(info, "market_cap",              0) or 0)
            pe_ratio   = float(getattr(info, "pe_ratio",                0) or 0)
            pb_ratio   = float(getattr(info, "pb_ratio",                0) or 0)
            free_float = float(getattr(info, "free_float",              0) or 0)
            foreign_r  = float(getattr(info, "foreign_ratio",           0) or 0)
            year_high  = float(getattr(info, "year_high",               0) or 0)
            year_low   = float(getattr(info, "year_low",                0) or 0)
            sma50      = float(getattr(info, "fifty_day_average",       0) or 0)
            sma200     = float(getattr(info, "two_hundred_day_average", 0) or 0)

            rsi       = float(t.get("rsi_14",              0) or 0)
            macd      = float(t.get("macd",                0) or 0)
            macd_sig  = float(t.get("macd_signal",         0) or 0)
            macd_hist = float(t.get("macd_histogram",      0) or 0)
            stoch_k   = float(t.get("stoch_k",             0) or 0)
            stoch_d   = float(t.get("stoch_d",             0) or 0)
            bb_upper  = float(t.get("bb_upper",            0) or 0)
            bb_lower  = float(t.get("bb_lower",            0) or 0)
            bb_mid    = float(t.get("bb_middle",           0) or 0)
            vwap      = float(t.get("vwap",                0) or 0)
            atr       = float(t.get("atr_14",              0) or 0)
            adx       = float(t.get("adx_14",              0) or 0)
            supertrend= float(t.get("supertrend",          0) or 0)
            st_dir    = float(t.get("supertrend_direction",0) or 0)
            bb_pct    = (fiyat - bb_lower) / (bb_upper - bb_lower) if (bb_upper - bb_lower) > 0 else 0.5

            try:
                etf_df     = h.etf_holders
                etf_toplam = float(etf_df['holding_weight_pct'].sum()) if not etf_df.empty else 0
                etf_sayisi = len(etf_df)
                etf_top5   = etf_df.nlargest(5, 'holding_weight_pct')[['name','holding_weight_pct','aum_usd']].values.tolist() if not etf_df.empty else []
                etf_df_full= etf_df
            except:
                etf_toplam, etf_sayisi, etf_top5, etf_df_full = 0, 0, [], pd.DataFrame()

            return {
                "fiyat": fiyat, "market_cap": market_cap, "pe_ratio": pe_ratio,
                "pb_ratio": pb_ratio, "free_float": free_float, "foreign_r": foreign_r,
                "year_high": year_high, "year_low": year_low, "sma50": sma50, "sma200": sma200,
                "rsi": rsi, "macd": macd, "macd_sig": macd_sig, "macd_hist": macd_hist,
                "stoch_k": stoch_k, "stoch_d": stoch_d,
                "bb_upper": bb_upper, "bb_lower": bb_lower, "bb_mid": bb_mid, "bb_pct": bb_pct,
                "vwap": vwap, "atr": atr, "adx": adx,
                "supertrend": supertrend, "st_dir": st_dir,
                "etf_toplam": etf_toplam, "etf_sayisi": etf_sayisi,
                "etf_top5": etf_top5, "etf_df": etf_df_full,
            }
        except Exception as e:
            return None

    def combo_puan_hesapla(v):
        """0-130 arası combo skor hesaplar"""
        puan = 0
        sinyaller = []
        f = v["fiyat"]

        # RSI
        rsi = v["rsi"]
        if 30 < rsi < 50:
            puan += 20; sinyaller.append(("✅", f"RSI dip bölgesinden çıkıyor ({rsi:.1f})"))
        elif rsi <= 30:
            puan += 12; sinyaller.append(("⚠️", f"RSI aşırı satım ({rsi:.1f})"))
        elif 50 <= rsi < 65:
            puan += 10; sinyaller.append(("🟡", f"RSI sağlıklı ({rsi:.1f})"))
        else:
            puan += 3;  sinyaller.append(("⚠️", f"RSI yüksek ({rsi:.1f})"))

        # MACD
        if v["macd_hist"] > 0 and v["macd"] > v["macd_sig"]:
            puan += 20; sinyaller.append(("✅", "MACD pozitif ve sinyal üzerinde"))
        elif v["macd_hist"] > 0:
            puan += 12; sinyaller.append(("🟡", f"MACD histogram pozitif ({v['macd_hist']:.3f})"))
        elif v["macd"] > v["macd_sig"]:
            puan += 8;  sinyaller.append(("🟡", "MACD sinyal çizgisini geçiyor"))

        # Stochastic
        sk, sd = v["stoch_k"], v["stoch_d"]
        if sk > sd and sk < 80 and sd < 60:
            puan += 15; sinyaller.append(("✅", f"Stochastic yükseliş K={sk:.1f} D={sd:.1f}"))
        elif sk > sd:
            puan += 8;  sinyaller.append(("🟡", f"Stochastic K>D ({sk:.1f})"))
        elif sk < 20:
            puan += 5;  sinyaller.append(("⚠️", f"Stochastic aşırı satım ({sk:.1f})"))

        # Bollinger
        if 0 <= v["bb_pct"] <= 0.2:
            puan += 15; sinyaller.append(("✅", f"Bollinger alt bandına yakın ({v['bb_pct']:.2f})"))
        elif 0.2 < v["bb_pct"] <= 0.4:
            puan += 8;  sinyaller.append(("🟡", "Bollinger orta-alt bölge"))

        # Supertrend
        if v["st_dir"] == 1:
            puan += 15; sinyaller.append(("✅", "Supertrend yükseliş trendi"))
        else:
            sinyaller.append(("🔴", "Supertrend düşüş trendi"))

        # VWAP
        if f > v["vwap"] > 0:
            puan += 10; sinyaller.append(("✅", f"Fiyat VWAP üzerinde ({v['vwap']:.2f})"))
        elif v["vwap"] > 0:
            sinyaller.append(("⚠️", f"Fiyat VWAP altında ({v['vwap']:.2f})"))

        # SMA Trend
        if f > v["sma50"] > v["sma200"] and v["sma50"] > 0:
            puan += 10; sinyaller.append(("✅", "Fiyat SMA50>SMA200 üzerinde"))
        elif f > v["sma50"] > 0:
            puan += 5;  sinyaller.append(("🟡", "Fiyat SMA50 üzerinde"))

        # ETF
        et = v["etf_toplam"]
        if et >= 1.0:
            puan += 15; sinyaller.append(("🌍", f"Güçlü ETF sahipliği %{et:.2f} ({v['etf_sayisi']} ETF)"))
        elif et >= 0.3:
            puan += 8;  sinyaller.append(("🟡", f"Orta ETF sahipliği %{et:.2f}"))
        elif et > 0:
            puan += 3;  sinyaller.append(("⚪", f"Düşük ETF sahipliği %{et:.2f}"))

        atr   = v["atr"] if v["atr"] > 0 else f * 0.02
        stop  = f - (1.5 * atr)
        h1    = f + (2.0 * atr)
        h2    = f + (3.5 * atr)
        ro    = (h1 - f) / (f - stop) if (f - stop) > 0 else 0

        return puan, sinyaller, stop, h1, h2, ro

    # ── YAN MENÜ ───────────────────────────────────────────────
    with st.sidebar:
        st.image("https://cdn-icons-png.flaticon.com/512/2422/2422176.png", width=80)
        st.write(f"👤 **Hoş geldin, {st.session_state.user.upper()}**")
        if st.button("🚪 Oturumu Kapat"):
            st.session_state.logged_in = False
            st.rerun()
        st.markdown("---")

        st.subheader("🛒 Portföye Ekle")
        secili_piyasa = st.selectbox("Piyasa Türü:", ["BIST (Türkiye)", "ABD Borsası", "Kripto Para", "TEFAS Fonu"])
        s = st.text_input("Sembol (örn: EREGL, AAPL, BTC, HVI):").upper()
        m = st.number_input("Maliyet:", min_value=0.0, format="%.4f")
        l = st.number_input("Adet / Lot:", min_value=0.0001, format="%.4f")

        if st.button("SQL'e Kaydet"):
            if s:
                sembol_kayit = s
                if secili_piyasa == "BIST (Türkiye)" and not sembol_kayit.endswith(".IS"):
                    sembol_kayit += ".IS"
                elif secili_piyasa == "Kripto Para" and not sembol_kayit.endswith("-USD"):
                    sembol_kayit += "-USD"
                conn = db_baglan()
                c = conn.cursor()
                c.execute("INSERT INTO portfoy VALUES (%s,%s,%s,%s,%s)", (st.session_state.user, sembol_kayit, m, l, secili_piyasa))
                conn.commit()
                conn.close()
                st.success(f"{sembol_kayit} portföye eklendi!")
                st.rerun()

        st.markdown("---")
        st.subheader("🗑️ Portföyden Çıkar")
        conn = db_baglan()
        c = conn.cursor()
        c.execute("SELECT sembol FROM portfoy WHERE username=%s", (st.session_state.user,))
        mevcut_semboller = [row[0] for row in c.fetchall()]
        conn.close()

        if mevcut_semboller:
            silinecek = st.selectbox("Silmek istediğinizi seçin:", mevcut_semboller)
            if st.button("🗑️ Seçileni Sil"):
                conn = db_baglan()
                c = conn.cursor()
                c.execute("DELETE FROM portfoy WHERE username=%s AND sembol=%s", (st.session_state.user, silinecek))
                conn.commit()
                conn.close()
                st.warning(f"{silinecek} portföyden silindi!")
                st.rerun()

    # ── ANA SEKMELER ───────────────────────────────────────────
    st.title("🚀 Arda Holding Yönetim Terminali")
    sekme_portfoy, sekme_grafik, sekme_combo, sekme_tarayici, sekme_etf, sekme_ai = st.tabs([
        "💼 Portföy", "📈 Grafik & Analiz", "🎯 Combo Skor", "⚡ Balina Avcısı", "🌍 ETF & Yabancı", "🤖 AI Danışman"
    ])

    # ──────────────────────────────────────────────────────────
    # SEKME 1: PORTFÖY
    # ──────────────────────────────────────────────────────────
    with sekme_portfoy:
        conn = db_baglan()
        c = conn.cursor()
        c.execute("SELECT sembol, maliyet, lot, piyasa FROM portfoy WHERE username=%s", (st.session_state.user,))
        data = c.fetchall()
        c.execute("SELECT tarih, toplam_deger FROM portfoy_gecmis WHERE username=%s ORDER BY tarih ASC", (st.session_state.user,))
        gecmis_data = c.fetchall()
        conn.close()

        df_p = pd.DataFrame(data, columns=["sembol", "maliyet", "lot", "piyasa"])

        if df_p.empty:
            st.info("Portföyünüz boş. Sol menüden ekleyebilirsiniz.")
        else:
            with st.spinner('Global piyasa verileri çekiliyor...'):
                guncel_fiyatlar = []
                for _, row in df_p.iterrows():
                    if row['piyasa'] == "TEFAS Fonu":
                        try:
                            crawler = Crawler()
                            bugun = datetime.now().strftime("%Y-%m-%d")
                            bas = (datetime.now() - timedelta(days=10)).strftime("%Y-%m-%d")
                            df_fon = crawler.fetch(start=bas, end=bugun, name=row['sembol'], columns=["date","price"])
                            guncel_fiyatlar.append(float(df_fon['price'].iloc[-1]) if not df_fon.empty else 0.0)
                        except:
                            guncel_fiyatlar.append(0.0)
                    else:
                        try:
                            fiyat = yf.Ticker(row['sembol']).history(period="1d")['Close'].iloc[-1]
                            guncel_fiyatlar.append(fiyat)
                        except:
                            guncel_fiyatlar.append(0.0)

                df_p['Anlık Fiyat']    = guncel_fiyatlar
                df_p['Toplam Maliyet'] = df_p['maliyet'] * df_p['lot']
                df_p['Güncel Değer']   = df_p['Anlık Fiyat'] * df_p['lot']
                df_p['Kâr/Zarar (TL)']= df_p['Güncel Değer'] - df_p['Toplam Maliyet']
                df_p['Kâr/Zarar (%)'] = df_p.apply(lambda r: (r['Kâr/Zarar (TL)'] / r['Toplam Maliyet'] * 100) if r['Toplam Maliyet'] > 0 else 0, axis=1)

                toplam_maliyet  = df_p['Toplam Maliyet'].sum()
                toplam_deger    = df_p['Güncel Değer'].sum()
                toplam_kar      = toplam_deger - toplam_maliyet
                toplam_yuzde    = (toplam_kar / toplam_maliyet * 100) if toplam_maliyet > 0 else 0

                pk1, pk2, pk3, pk4 = st.columns(4)
                pk1.metric("💰 Toplam Maliyet", f"{toplam_maliyet:,.2f} TL")
                pk2.metric("💳 Güncel Değer",   f"{toplam_deger:,.2f} TL")
                pk3.metric("📊 Kâr / Zarar",    f"{toplam_kar:+,.2f} TL", f"%{toplam_yuzde:.2f}")
                with pk4:
                    if st.button("💾 Günün Kapanışını Kaydet"):
                        bugun_tarih = datetime.now().strftime("%Y-%m-%d")
                        conn = db_baglan()
                        c = conn.cursor()
                        c.execute("DELETE FROM portfoy_gecmis WHERE username=%s AND tarih=%s", (st.session_state.user, bugun_tarih))
                        c.execute("INSERT INTO portfoy_gecmis VALUES (%s,%s,%s)", (st.session_state.user, bugun_tarih, float(toplam_deger)))
                        conn.commit()
                        conn.close()
                        st.success("Kaydedildi!")
                        st.rerun()

                st.markdown("---")
                col_tablo, col_grafik = st.columns([1.5, 1])
                with col_tablo:
                    st.write("📋 **Portföy Detayları**")
                    st.dataframe(df_p.style.format({
                        "maliyet": "{:.4f}", "lot": "{:.4f}", "Anlık Fiyat": "{:.4f}",
                        "Toplam Maliyet": "{:.2f}", "Güncel Değer": "{:.2f}",
                        "Kâr/Zarar (TL)": "{:.2f}", "Kâr/Zarar (%)": "{:.2f}%"
                    }).map(lambda x: 'color: #00ff88' if isinstance(x, (int,float)) and x > 0 else ('color: #ff4444' if isinstance(x, (int,float)) and x < 0 else ''),
                           subset=['Kâr/Zarar (TL)', 'Kâr/Zarar (%)']),
                    use_container_width=True, hide_index=True)

                with col_grafik:
                    st.write("🍕 **Portföy Dağılımı**")
                    if df_p['Güncel Değer'].sum() > 0:
                        fig_pie = px.pie(df_p, values='Güncel Değer', names='sembol', hole=0.4)
                        fig_pie.update_layout(margin=dict(t=0,b=0,l=0,r=0), height=300, template="plotly_dark")
                        st.plotly_chart(fig_pie, use_container_width=True)

                st.markdown("---")
                st.write("📈 **Büyüme Grafiği**")
                if gecmis_data:
                    df_gecmis = pd.DataFrame(gecmis_data, columns=["Tarih", "Toplam Değer"])
                    fig_line = px.line(df_gecmis, x="Tarih", y="Toplam Değer", markers=True, line_shape="spline")
                    fig_line.update_traces(line_color='#00bfff', line_width=3, marker=dict(size=8, color='white'))
                    fig_line.update_layout(height=400, template="plotly_dark", margin=dict(t=10,b=10,l=10,r=10))
                    st.plotly_chart(fig_line, use_container_width=True)
                else:
                    st.info("Büyümeyi görmek için 'Günün Kapanışını Kaydet' butonunu kullan!")

    # ──────────────────────────────────────────────────────────
    # SEKME 2: GRAFİK & ANALİZ (SEÇİLEBİLİR İNDİKATÖRLER)
    # ──────────────────────────────────────────────────────────
    with sekme_grafik:
        col_sol, col_sag = st.columns([2, 1])
        with col_sol:
            aranan = st.text_input("Sembol (Örn: ASELS.IS, AAPL, BTC-USD):", placeholder="Sembol gir...").upper()
        with col_sag:
            periyot = st.selectbox("Periyot:", ["1mo", "3mo", "6mo", "1y", "2y"], index=1)

        # İndikatör seçenekleri — kullanıcı açıp kapayabilir
        st.write("**📊 İndikatör Seçenekleri:**")
        ic1, ic2, ic3, ic4, ic5, ic6, ic7, ic8 = st.columns(8)
        goster_sma20      = ic1.checkbox("SMA 20",      value=True)
        goster_sma50      = ic2.checkbox("SMA 50",      value=True)
        goster_bb         = ic3.checkbox("Bollinger",   value=False)
        goster_vwap       = ic4.checkbox("VWAP",        value=False)
        goster_supertrend = ic5.checkbox("Supertrend",  value=False)
        goster_rsi        = ic6.checkbox("RSI",         value=True)
        goster_macd       = ic7.checkbox("MACD",        value=True)
        goster_hacim      = ic8.checkbox("Hacim",       value=True)

        if aranan:
            try:
                with st.spinner(f'{aranan} yükleniyor...'):
                    df = yf.Ticker(aranan).history(period=periyot)
                    if not df.empty:
                        # İndikatörleri hesapla
                        df['SMA20'] = ta.trend.sma_indicator(df['Close'], window=20)
                        df['SMA50'] = ta.trend.sma_indicator(df['Close'], window=50)
                        df['RSI']   = ta.momentum.rsi(df['Close'], window=14)

                        macd_ind          = ta.trend.MACD(df['Close'])
                        df['MACD']        = macd_ind.macd()
                        df['MACD_signal'] = macd_ind.macd_signal()
                        df['MACD_hist']   = macd_ind.macd_diff()

                        bb_ind          = ta.volatility.BollingerBands(df['Close'], window=20)
                        df['BB_upper']  = bb_ind.bollinger_hband()
                        df['BB_lower']  = bb_ind.bollinger_lband()
                        df['BB_mid']    = bb_ind.bollinger_mavg()

                        # VWAP
                        df['VWAP'] = (df['Volume'] * (df['High'] + df['Low'] + df['Close']) / 3).cumsum() / df['Volume'].cumsum()

                        # Supertrend (ATR tabanlı basit versiyon)
                        atr = ta.volatility.AverageTrueRange(df['High'], df['Low'], df['Close'], window=14).average_true_range()
                        df['ST_upper'] = (df['High'] + df['Low']) / 2 + (3 * atr)
                        df['ST_lower'] = (df['High'] + df['Low']) / 2 - (3 * atr)

                        anlik  = df['Close'].iloc[-1]
                        degisim= ((anlik - df['Close'].iloc[-2]) / df['Close'].iloc[-2]) * 100

                        # Metrikler
                        k1, k2, k3, k4, k5 = st.columns(5)
                        k1.metric("🎯 Kapanış",   f"{anlik:.2f}",                  f"%{degisim:.2f}")
                        k2.metric("📊 Hacim",     f"{int(df['Volume'].iloc[-1]):,}")
                        k3.metric("📈 RSI (14)",  f"{df['RSI'].iloc[-1]:.1f}")
                        k4.metric("📊 MACD",      "🟢 AL" if df['MACD'].iloc[-1] > df['MACD_signal'].iloc[-1] else "🔴 SAT")
                        k5.metric("📉 BB%",       f"{((anlik - df['BB_lower'].iloc[-1]) / (df['BB_upper'].iloc[-1] - df['BB_lower'].iloc[-1])):.2f}" if (df['BB_upper'].iloc[-1] - df['BB_lower'].iloc[-1]) > 0 else "N/A")

                        df_g = df.tail(120)

                        # Kaç alt panel lazım?
                        alt_paneller = sum([goster_rsi, goster_macd, goster_hacim])
                        row_heights  = [0.55] + [0.15] * alt_paneller if alt_paneller > 0 else [1.0]
                        toplam_row   = 1 + alt_paneller

                        fig = make_subplots(rows=toplam_row, cols=1, shared_xaxes=True,
                                            row_heights=row_heights, vertical_spacing=0.03)

                        # Mum grafiği
                        fig.add_trace(go.Candlestick(
                            x=df_g.index, open=df_g['Open'], high=df_g['High'],
                            low=df_g['Low'], close=df_g['Close'], name="Fiyat",
                            increasing_line_color='#00ff88', decreasing_line_color='#ff4444'
                        ), row=1, col=1)

                        # Seçili indikatörler
                        if goster_sma20:
                            fig.add_trace(go.Scatter(x=df_g.index, y=df_g['SMA20'], line=dict(color='orange', width=1.5), name='SMA20'), row=1, col=1)
                        if goster_sma50:
                            fig.add_trace(go.Scatter(x=df_g.index, y=df_g['SMA50'], line=dict(color='#00bfff', width=1.5), name='SMA50'), row=1, col=1)
                        if goster_bb:
                            fig.add_trace(go.Scatter(x=df_g.index, y=df_g['BB_upper'], line=dict(color='rgba(255,255,100,0.5)', width=1, dash='dot'), name='BB Üst'), row=1, col=1)
                            fig.add_trace(go.Scatter(x=df_g.index, y=df_g['BB_lower'], line=dict(color='rgba(255,255,100,0.5)', width=1, dash='dot'), name='BB Alt', fill='tonexty', fillcolor='rgba(255,255,100,0.05)'), row=1, col=1)
                        if goster_vwap:
                            fig.add_trace(go.Scatter(x=df_g.index, y=df_g['VWAP'], line=dict(color='#ff69b4', width=1.5, dash='dash'), name='VWAP'), row=1, col=1)
                        if goster_supertrend:
                            fig.add_trace(go.Scatter(x=df_g.index, y=df_g['ST_lower'], line=dict(color='rgba(0,255,100,0.4)', width=1), name='ST Destek'), row=1, col=1)
                            fig.add_trace(go.Scatter(x=df_g.index, y=df_g['ST_upper'], line=dict(color='rgba(255,50,50,0.4)', width=1), name='ST Direnç'), row=1, col=1)

                        # Alt paneller
                        panel = 2
                        if goster_rsi:
                            fig.add_trace(go.Scatter(x=df_g.index, y=df_g['RSI'], line=dict(color='yellow', width=1.5), name='RSI'), row=panel, col=1)
                            fig.add_hline(y=70, line_dash="dash", line_color="red",   row=panel, col=1)
                            fig.add_hline(y=30, line_dash="dash", line_color="green", row=panel, col=1)
                            fig.update_yaxes(title_text="RSI", row=panel, col=1)
                            panel += 1
                        if goster_macd:
                            fig.add_trace(go.Scatter(x=df_g.index, y=df_g['MACD'],        line=dict(color='cyan',    width=1.5), name='MACD'), row=panel, col=1)
                            fig.add_trace(go.Scatter(x=df_g.index, y=df_g['MACD_signal'], line=dict(color='magenta', width=1.5), name='Sinyal'), row=panel, col=1)
                            fig.add_trace(go.Bar(x=df_g.index, y=df_g['MACD_hist'],
                                                 marker_color=['#00ff88' if v >= 0 else '#ff4444' for v in df_g['MACD_hist']],
                                                 name='Histogram'), row=panel, col=1)
                            fig.update_yaxes(title_text="MACD", row=panel, col=1)
                            panel += 1
                        if goster_hacim:
                            fig.add_trace(go.Bar(x=df_g.index, y=df_g['Volume'],
                                                 marker_color=['#00ff88' if c >= o else '#ff4444' for c, o in zip(df_g['Close'], df_g['Open'])],
                                                 name='Hacim'), row=panel, col=1)
                            fig.update_yaxes(title_text="Hacim", row=panel, col=1)

                        fig.update_layout(
                            xaxis_rangeslider_visible=False,
                            margin=dict(l=10, r=10, t=20, b=10),
                            height=700, template="plotly_dark", showlegend=True,
                            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
                        )
                        st.plotly_chart(fig, use_container_width=True)
                    else:
                        st.warning("Veri bulunamadı.")
            except Exception as e:
                st.error(f"Hata: {e}")

    # ──────────────────────────────────────────────────────────
    # SEKME 3: COMBO SKOR (borsapy tabanlı)
    # ──────────────────────────────────────────────────────────
    with sekme_combo:
        st.subheader("🎯 Combo Skor Analizi (0-130 Puan)")
        st.caption("Teknik analiz + ETF kurumsal sahipliği bir arada — ne kadar yüksekse o kadar güçlü sinyal.")

        combo_sembol = st.text_input("BIST Hisse Sembolü (Örn: THYAO, EREGL):", key="combo_input").upper().replace(".IS","")

        if st.button("🔍 Combo Analiz Et") and combo_sembol:
            with st.spinner(f"{combo_sembol} analiz ediliyor..."):
                v = borsapy_veri_cek(combo_sembol)

            if not v:
                st.error(f"❌ {combo_sembol} verisi alınamadı.")
            else:
                puan, sinyaller, stop, h1, h2, ro = combo_puan_hesapla(v)

                # Renk ve karar
                if   puan >= 100: renk = "🟢"; karar = "ÇOK GÜÇLÜ FIRSAT"
                elif puan >= 80:  renk = "🟡"; karar = "GÜÇLÜ SİNYAL"
                elif puan >= 60:  renk = "🟠"; karar = "ORTA KUVVETLİ"
                else:             renk = "🔴"; karar = "ZAYIF SİNYAL"

                # Skor göstergesi
                col_skor, col_detay = st.columns([1, 2])
                with col_skor:
                    st.metric(f"{renk} COMBO SKOR", f"{puan} / 130")
                    st.progress(puan / 130)
                    st.write(f"**{karar}**")
                    st.markdown("---")
                    st.write(f"💰 **Fiyat:** {v['fiyat']:.2f} TL")
                    st.write(f"🎯 **Hedef 1:** {h1:.2f} TL (+{((h1/v['fiyat'])-1)*100:.1f}%)")
                    st.write(f"🎯 **Hedef 2:** {h2:.2f} TL (+{((h2/v['fiyat'])-1)*100:.1f}%)")
                    st.write(f"🛑 **Stop-Loss:** {stop:.2f} TL (-{((1-(stop/v['fiyat']))*100):.1f}%)")
                    st.write(f"⚖️ **Risk/Ödül:** 1 / {ro:.1f}")

                with col_detay:
                    st.write("**📌 Sinyal Detayları:**")
                    for emoji, metin in sinyaller:
                        st.write(f"{emoji} {metin}")

                    st.markdown("---")
                    # İndikatör tablosu
                    st.write("**📊 İndikatör Özeti:**")
                    ind_df = pd.DataFrame({
                        "İndikatör": ["RSI(14)", "MACD Hist", "Stoch K/D", "BB%", "VWAP", "ADX", "Supertrend", "SMA50", "SMA200", "ETF Sahipliği"],
                        "Değer": [
                            f"{v['rsi']:.1f}",
                            f"{v['macd_hist']:.3f}",
                            f"{v['stoch_k']:.1f} / {v['stoch_d']:.1f}",
                            f"{v['bb_pct']:.2f}",
                            f"{v['vwap']:.2f}",
                            f"{v['adx']:.1f}",
                            "⬆️ Yukarı" if v['st_dir']==1 else "⬇️ Aşağı",
                            f"{v['sma50']:.2f}",
                            f"{v['sma200']:.2f}",
                            f"%{v['etf_toplam']:.3f} ({v['etf_sayisi']} ETF)",
                        ]
                    })
                    st.dataframe(ind_df, use_container_width=True, hide_index=True)

    # ──────────────────────────────────────────────────────────
    # SEKME 4: BALİNA TARAYICI
    # ──────────────────────────────────────────────────────────
    with sekme_tarayici:
        st.info("💡 BIST hisseleri taranır. Yüksek hacim + güçlü momentum tespit edilir.")

        HISSELER_TARAMA = [
            "THYAO.IS","EREGL.IS","ASELS.IS","KCHOL.IS","FROTO.IS","TUPRS.IS",
            "ISCTR.IS","AKBNK.IS","YKBNK.IS","GARAN.IS","SAHOL.IS","SASA.IS",
            "HEKTS.IS","BIMAS.IS","SISE.IS","TCELL.IS","TOASO.IS","PETKM.IS",
            "EKGYO.IS","ENKAI.IS","ARCLK.IS","VESTL.IS","MAVI.IS","PGSUS.IS","QUAGR:IS"
        ]

        # Tarama kriterleri — kullanıcı ayarlayabilir
        with st.expander("⚙️ Tarama Kriterleri (Özelleştir)"):
            tc1, tc2, tc3 = st.columns(3)
            hacim_esik = tc1.slider("Minimum Hacim Çarpanı (x):", 1.2, 5.0, 1.5, 0.1)
            mfi_esik   = tc2.slider("Minimum MFI:", 50, 90, 70, 5)
            rsi_max    = tc3.slider("Maksimum RSI (aşırı alım filtresi):", 60, 90, 75, 5)

        def hisse_analiz_et(sembol):
            try:
                df = yf.Ticker(sembol).history(period="5d", interval="15m")
                if df.empty or len(df) < 15: return None
                df['MFI'] = ta.volume.money_flow_index(df['High'], df['Low'], df['Close'], df['Volume'], window=14)
                df['RSI'] = ta.momentum.rsi(df['Close'], window=14)
                s_hacim   = float(df['Volume'].dropna().iloc[-1])
                o_hacim   = float(df['Volume'].dropna().tail(11).head(10).mean())
                fiyat     = float(df['Close'].dropna().iloc[-1])
                s_mfi     = float(df['MFI'].dropna().iloc[-1])
                s_rsi     = float(df['RSI'].dropna().iloc[-1])
                if s_hacim > (o_hacim * hacim_esik) and s_mfi > mfi_esik and s_rsi < rsi_max:
                    return {"sembol": sembol, "fiyat": fiyat, "hacim_oran": s_hacim/o_hacim, "mfi": s_mfi, "rsi": s_rsi}
            except:
                pass
            return None

        if st.button("🚀 Hisseleri Tara"):
            with st.spinner("Taranıyor..."):
                with concurrent.futures.ThreadPoolExecutor(max_workers=10) as ex:
                    sonuclar = list(ex.map(hisse_analiz_et, HISSELER_TARAMA))

            bulunanlar = [s for s in sonuclar if s]
            if bulunanlar:
                st.success(f"✅ {len(bulunanlar)} hisse bulundu!")
                cols = st.columns(3)
                for i, s in enumerate(bulunanlar):
                    with cols[i % 3]:
                        with st.container(border=True):
                            st.success(f"🔥 **{s['sembol']}**")
                            st.metric("Fiyat", f"{s['fiyat']:.2f} TL")
                            st.write(f"📊 Hacim: **{s['hacim_oran']:.1f}x** | MFI: **{s['mfi']:.1f}** | RSI: **{s['rsi']:.1f}**")
            else:
                st.info("Şu an kriterlere uyan hisse bulunamadı. Kriterleri gevşetmeyi dene.")

    # ──────────────────────────────────────────────────────────
    # SEKME 5: ETF & YABANCI YATIRIMCI
    # ──────────────────────────────────────────────────────────
    with sekme_etf:
        st.subheader("🌍 ETF Sahiplik & Yabancı Yatırımcı Analizi")
        st.caption("Vanguard, iShares gibi büyük küresel ETF'lerin hangi hisseleri tuttuğunu gösterir.")

        etf_sembol = st.text_input("BIST Hisse Sembolü (Örn: THYAO, GARAN):", key="etf_input").upper().replace(".IS","")

        if st.button("🔍 ETF & Yabancı Analiz Et") and etf_sembol:
            with st.spinner(f"{etf_sembol} ETF verisi çekiliyor..."):
                v = borsapy_veri_cek(etf_sembol)

            if not v:
                st.error(f"❌ {etf_sembol} verisi alınamadı.")
            else:
                # Yabancı özeti
                e1, e2, e3, e4 = st.columns(4)
                e1.metric("👥 Yabancı Oranı",   f"%{v['foreign_r']:.1f}")
                e2.metric("📊 Halka Açıklık",   f"%{v['free_float']:.1f}")
                e3.metric("🌍 ETF Sayısı",       f"{v['etf_sayisi']} adet")
                e4.metric("⚖️ ETF Toplam Ağırlık", f"%{v['etf_toplam']:.3f}")

                st.markdown("---")

                if not v['etf_df'].empty:
                    col_tablo, col_grafik = st.columns([1.5, 1])
                    with col_tablo:
                        st.write("**📋 En Büyük ETF Sahipleri:**")
                        etf_goster = v['etf_df'].nlargest(15, 'holding_weight_pct')[['name','holding_weight_pct','aum_usd','focus']].copy()
                        etf_goster.columns = ['ETF Adı', 'Ağırlık (%)', 'AUM ($)', 'Odak']
                        etf_goster['AUM ($)'] = etf_goster['AUM ($)'].apply(lambda x: para_fmt(x) if pd.notna(x) else '-')
                        st.dataframe(etf_goster, use_container_width=True, hide_index=True)

                    with col_grafik:
                        st.write("**🍕 ETF Dağılımı (Top 10):**")
                        top10 = v['etf_df'].nlargest(10, 'holding_weight_pct')
                        fig_etf = px.bar(top10, x='holding_weight_pct', y='name',
                                        orientation='h', color='holding_weight_pct',
                                        color_continuous_scale='Blues',
                                        labels={'holding_weight_pct': 'Ağırlık (%)', 'name': ''})
                        fig_etf.update_layout(height=400, template="plotly_dark", showlegend=False,
                                             coloraxis_showscale=False, margin=dict(l=0,r=10,t=10,b=10))
                        st.plotly_chart(fig_etf, use_container_width=True)
                else:
                    st.warning("Bu hisse için ETF sahiplik verisi bulunamadı.")

    # ──────────────────────────────────────────────────────────
    # SEKME 6: AI DANIŞMAN (GEMINI)
    # ──────────────────────────────────────────────────────────
    with sekme_ai:
        st.header("🤖 Arda Holding Yapay Zeka Finans Asistanı")

        if "GEMINI_API_KEY" not in st.secrets:
            st.warning("⚠️ Yapay Zeka henüz aktif değil!")
            st.info("1. [aistudio.google.com](https://aistudio.google.com/) adresine gidip ücretsiz API Key oluştur.\n"
                    "2. Streamlit Secrets bölümüne `GEMINI_API_KEY = 'anahtarin'` ekle.\n"
                    "3. Sayfayı yenile.")
        else:
            genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
            model = genai.GenerativeModel('gemini-1.5-flash')

            ai_sembol = st.text_input("Analiz edilecek hisse (Örn: THYAO, AAPL):", key="ai_input").upper()

            # Combo skoru da AI'ya ver seçeneği
            combo_ekle = st.checkbox("🎯 Combo Skor analizini de AI'ya ver (BIST hisseleri için)", value=True)

            if st.button("🧠 Hisseyi Analiz Et") and ai_sembol:
                with st.spinner("Yapay zeka rapor hazırlıyor..."):
                    try:
                        hisse  = yf.Ticker(ai_sembol if "." in ai_sembol else ai_sembol + ".IS")
                        info   = hisse.info
                        fiyat  = hisse.history(period="1d")['Close'].iloc[-1]
                        sirket = info.get('longName', ai_sembol)
                        sektor = info.get('sector', 'Bilinmiyor')
                        fko    = info.get('trailingPE', 'Bilinmiyor')

                        # Combo skor ekle
                        combo_bilgi = ""
                        if combo_ekle:
                            sembol_temiz = ai_sembol.replace(".IS","")
                            v = borsapy_veri_cek(sembol_temiz)
                            if v:
                                puan, sinyaller, stop, h1, h2, ro = combo_puan_hesapla(v)
                                combo_bilgi = f"""
Teknik Analiz Skoru: {puan}/130
RSI: {v['rsi']:.1f}, MACD Histogram: {v['macd_hist']:.3f}
Supertrend: {'Yükseliş' if v['st_dir']==1 else 'Düşüş'} yönünde
Yabancı Oranı: %{v['foreign_r']:.1f}, ETF Sahipliği: {v['etf_sayisi']} ETF
Hedef Fiyat 1: {h1:.2f} TL, Stop-Loss: {stop:.2f} TL
"""

                        prompt = f"""
Sen Arda Holding'in baş finansal danışmanısın. Karşındaki kişi holdingin CEO'su Arda.
'{sirket}' ({ai_sembol}) hissesi hakkında profesyonel, anlaşılır ve Türkçe bir rapor sun.

Şirket Bilgileri:
- Sektör: {sektor}
- Anlık Fiyat: {fiyat:.2f}
- F/K Oranı: {fko}
{combo_bilgi}

Lütfen şunları anlat:
1. Şirket ne iş yapıyor ve sektörde konumu nasıl?
2. Teknik göstergeler ne söylüyor? (verilen değerleri yorumla)
3. Risk faktörleri neler?
4. Kısa-orta vadeli beklenti ve yatırımcı için tavsiye.

Raporu madde madde, net ve özlü yaz.
"""
                        cevap = model.generate_content(prompt)
                        st.markdown(f"### 📑 {sirket} — AI Raporu")
                        st.write(cevap.text)

                    except Exception as e:
                        st.error(f"Hata: {e}")
