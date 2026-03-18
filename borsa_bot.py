"""
BIST Analiz Botu — borsapy tabanlı tam versiyon
================================================
Kurulum:
    pip install borsapy "python-telegram-bot[job-queue]"

Komutlar:
    /fiyat    THYAO    — Anlık fiyat + özet
    /detay    THYAO    — Tam teknik analiz raporu
    /yildiz            — En güçlü yükseliş adayları
    /top5              — Günün en iyi 5 hissesi
    /kisa              — 30dk yükseliş adayları (piyasa saatinde)
    /kisadetay THYAO   — Tek hisse kısa vade analizi
    /etf      THYAO    — Hangi büyük ETF'ler tutuyor?
    /kurumsal          — ETF ağırlığı en yüksek hisseler
    /yabanci  THYAO    — Yabancı oranı + F/K + ETF
    /combo    THYAO    — Teknik + Kurumsal combo skor
"""

import borsapy as bp
import os
from dotenv import load_dotenv
load_dotenv()
import pandas as pd
from datetime import datetime
from zoneinfo import ZoneInfo
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

# ── AYARLAR ──────────────────────────────────────────────────
TOKEN   = os.getenv("TOKEN")
CHAT_ID = os.getenv("CHAT_ID")
ISTANBUL_TZ = ZoneInfo("Europe/Istanbul")

HISSELER = [
    "AEFES", "AGHOL", "AKBNK", "AKCNS", "AKFGY", "AKSA", "AKSEN", "ALARK",
    "ALBRK", "ALFAS", "ARCLK", "ASELS", "ASTOR", "BERA", "BIMAS", "BIOEN",
    "BOBET", "BRSAN", "BRYAT", "BUCIM", "CANTE", "CCOLA", "CIMSA", "CWENE",
    "DOAS", "DOHOL", "ECILC", "EGEEN", "EKGYO", "ENJSA", "ENKAI", "EREGL",
    "EUPWR", "EUREN", "FROTO", "GARAN", "GENIL", "GESAN", "GUBRF", "GWIND",
    "HALKB", "HEKTS", "ISCTR", "ISDMR", "ISGYO", "ISMEN", "IZENR",
    "KCAER", "KCHOL", "KLSER", "KMPUR", "KONTR", "KONYA",
    "KRDMD", "MAVI", "MIATK", "MGROS", "ODAS", "OTKAR", "OYAKC", "PETKM",
    "PGSUS", "QUAGR", "SAHOL", "SASA", "SDTTR", "SISE", "SKBNK", "SMRTG",
    "SOKM", "TABGD", "TAVHL", "TCELL", "THYAO", "TKFEN", "TOASO", "TSKB",
    "TTKOM", "TTRAK", "TUKAS", "TUPRS", "ULKER", "VAKBN", "VESBE", "VESTL",
    "YEOTK", "YKBNK", "YYLGD", "ZOREN", "AGROT", "BINHO", "REEDR", "KAYSE",
    "BOSSA", "KORDS", "GOLTS", "EBEBK"
]


# ── YARDIMCI ─────────────────────────────────────────────────
def piyasa_acik_mi() -> bool:
    simdi = datetime.now(ISTANBUL_TZ)
    if simdi.weekday() >= 5:
        return False
    saat = simdi.hour * 60 + simdi.minute
    return (10 * 60) <= saat <= (18 * 60)

def para_fmt(t: float) -> str:
    if abs(t) >= 1e9: return f"{t/1e9:.2f}B $"
    if abs(t) >= 1e6: return f"{t/1e6:.1f}M $"
    return f"{t:,.0f} $"


# ── TEMEL VERİ ÇEKİCİ ────────────────────────────────────────
def hisse_veri_cek(sembol: str) -> dict | None:
    try:
        h    = bp.Ticker(sembol)
        info = h.fast_info
        t    = h.technicals().latest

        fiyat      = float(getattr(info, "last_price",               0) or 0)
        market_cap = float(getattr(info, "market_cap",               0) or 0)
        pe_ratio   = float(getattr(info, "pe_ratio",                 0) or 0)
        pb_ratio   = float(getattr(info, "pb_ratio",                 0) or 0)
        free_float = float(getattr(info, "free_float",               0) or 0)
        foreign_r  = float(getattr(info, "foreign_ratio",            0) or 0)
        year_high  = float(getattr(info, "year_high",                0) or 0)
        year_low   = float(getattr(info, "year_low",                 0) or 0)
        sma50      = float(getattr(info, "fifty_day_average",        0) or 0)
        sma200     = float(getattr(info, "two_hundred_day_average",  0) or 0)

        rsi       = float(t.get("rsi_14",             0) or 0)
        macd      = float(t.get("macd",               0) or 0)
        macd_sig  = float(t.get("macd_signal",        0) or 0)
        macd_hist = float(t.get("macd_histogram",     0) or 0)
        stoch_k   = float(t.get("stoch_k",            0) or 0)
        stoch_d   = float(t.get("stoch_d",            0) or 0)
        bb_upper  = float(t.get("bb_upper",           0) or 0)
        bb_lower  = float(t.get("bb_lower",           0) or 0)
        bb_mid    = float(t.get("bb_middle",          0) or 0)
        vwap      = float(t.get("vwap",               0) or 0)
        atr       = float(t.get("atr_14",             0) or 0)
        adx       = float(t.get("adx_14",             0) or 0)
        supertrend= float(t.get("supertrend",         0) or 0)
        st_dir    = float(t.get("supertrend_direction",0) or 0)
        bb_pct    = (fiyat - bb_lower) / (bb_upper - bb_lower) if (bb_upper - bb_lower) > 0 else 0.5

        try:
            etf_df     = h.etf_holders
            etf_toplam = float(etf_df['holding_weight_pct'].sum()) if not etf_df.empty else 0
            etf_sayisi = len(etf_df)
            etf_top3   = etf_df.nlargest(3, 'holding_weight_pct')[['name','holding_weight_pct']].values.tolist() if not etf_df.empty else []
        except:
            etf_toplam, etf_sayisi, etf_top3 = 0, 0, []

        return {
            "sembol": sembol, "fiyat": fiyat, "market_cap": market_cap,
            "pe_ratio": pe_ratio, "pb_ratio": pb_ratio,
            "free_float": free_float, "foreign_r": foreign_r,
            "year_high": year_high, "year_low": year_low,
            "sma50": sma50, "sma200": sma200,
            "rsi": rsi, "macd": macd, "macd_sig": macd_sig, "macd_hist": macd_hist,
            "stoch_k": stoch_k, "stoch_d": stoch_d,
            "bb_upper": bb_upper, "bb_lower": bb_lower, "bb_mid": bb_mid, "bb_pct": bb_pct,
            "vwap": vwap, "atr": atr, "adx": adx,
            "supertrend": supertrend, "st_dir": st_dir,
            "etf_toplam": etf_toplam, "etf_sayisi": etf_sayisi, "etf_top3": etf_top3,
        }
    except Exception as e:
        print(f"Veri hatası ({sembol}): {e}")
        return None


# ── PUANLAMA ─────────────────────────────────────────────────
def puan_hesapla(v: dict) -> tuple:
    puan = 0
    sinyaller = []
    f = v["fiyat"]

    # RSI (0-20p)
    rsi = v["rsi"]
    if 30 < rsi < 50:
        puan += 20
        sinyaller.append(f"✅ RSI dip bölgesinden çıkıyor ({rsi:.1f})")
    elif rsi <= 30:
        puan += 12
        sinyaller.append(f"⚠️ RSI aşırı satım ({rsi:.1f})")
    elif 50 <= rsi < 65:
        puan += 10
        sinyaller.append(f"🟡 RSI sağlıklı ({rsi:.1f})")
    elif rsi >= 65:
        puan += 3
        sinyaller.append(f"⚠️ RSI yüksek ({rsi:.1f})")

    # MACD (0-20p)
    if v["macd_hist"] > 0 and v["macd"] > v["macd_sig"]:
        puan += 20
        sinyaller.append("✅ MACD pozitif ve sinyal üzerinde")
    elif v["macd_hist"] > 0:
        puan += 12
        sinyaller.append(f"🟡 MACD histogram pozitif ({v['macd_hist']:.3f})")
    elif v["macd"] > v["macd_sig"]:
        puan += 8
        sinyaller.append("🟡 MACD sinyal çizgisini geçiyor")

    # Stochastic (0-15p)
    sk, sd = v["stoch_k"], v["stoch_d"]
    if sk > sd and sk < 80 and sd < 60:
        puan += 15
        sinyaller.append(f"✅ Stochastic yükseliş K={sk:.1f} D={sd:.1f}")
    elif sk > sd:
        puan += 8
        sinyaller.append(f"🟡 Stochastic K>D ({sk:.1f})")
    elif sk < 20:
        puan += 5
        sinyaller.append(f"⚠️ Stochastic aşırı satım ({sk:.1f})")

    # Bollinger (0-15p)
    if 0 <= v["bb_pct"] <= 0.2:
        puan += 15
        sinyaller.append(f"✅ Bollinger alt bandına yakın (BB%={v['bb_pct']:.2f})")
    elif 0.2 < v["bb_pct"] <= 0.4:
        puan += 8
        sinyaller.append("🟡 Bollinger orta-alt bölge")

    # Supertrend (0-15p)
    if v["st_dir"] == 1:
        puan += 15
        sinyaller.append("✅ Supertrend yükseliş trendi")
    else:
        sinyaller.append("🔴 Supertrend düşüş trendi")

    # VWAP (0-10p)
    if f > v["vwap"] > 0:
        puan += 10
        sinyaller.append(f"✅ Fiyat VWAP üzerinde ({v['vwap']:.2f})")
    elif v["vwap"] > 0:
        sinyaller.append(f"⚠️ Fiyat VWAP altında ({v['vwap']:.2f})")

    # SMA Trend (0-10p)
    if f > v["sma50"] > v["sma200"] and v["sma50"] > 0 and v["sma200"] > 0:
        puan += 10
        sinyaller.append("✅ Fiyat SMA50>SMA200 üzerinde (güçlü trend)")
    elif f > v["sma50"] > 0:
        puan += 5
        sinyaller.append("🟡 Fiyat SMA50 üzerinde")

    # ETF Kurumsal (0-15p)
    et = v["etf_toplam"]
    if et >= 1.0:
        puan += 15
        sinyaller.append(f"🌍 Güçlü ETF sahipliği: %{et:.2f} ({v['etf_sayisi']} ETF)")
    elif et >= 0.3:
        puan += 8
        sinyaller.append(f"🟡 Orta ETF sahipliği: %{et:.2f} ({v['etf_sayisi']} ETF)")
    elif et > 0:
        puan += 3
        sinyaller.append(f"⚪ Düşük ETF sahipliği: %{et:.2f}")

    atr   = v["atr"] if v["atr"] > 0 else f * 0.02
    stop  = f - (1.5 * atr)
    h1    = f + (2.0 * atr)
    h2    = f + (3.5 * atr)
    ro    = (h1 - f) / (f - stop) if (f - stop) > 0 else 0

    return puan, sinyaller, stop, h1, h2, ro


# ── KOMUTLAR ─────────────────────────────────────────────────

async def fiyat_sorgula(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("⚠️ Örnek: `/fiyat THYAO`", parse_mode='Markdown')
        return
    sembol = context.args[0].upper().replace(".IS", "")
    await update.message.reply_text(f"⏳ {sembol} verisi çekiliyor...")
    v = hisse_veri_cek(sembol)
    if not v:
        await update.message.reply_text(f"❌ {sembol} verisi alınamadı.")
        return
    puan, sin, stop, h1, h2, ro = puan_hesapla(v)
    yh_pct = ((v['fiyat'] / v['year_low']) - 1) * 100 if v['year_low'] > 0 else 0
    mesaj = (
        f"📊 *{sembol}* — {v['fiyat']:.2f} TL\n\n"
        f"📈 52H: {v['year_low']:.2f} — {v['year_high']:.2f} (dipten +%{yh_pct:.1f})\n"
        f"💼 Piyasa Değeri: {para_fmt(v['market_cap'])}\n"
        f"📉 F/K: {v['pe_ratio']:.1f} | F/DD: {v['pb_ratio']:.1f}\n"
        f"🌍 Yabancı: %{v['foreign_r']:.1f} | Halka Açık: %{v['free_float']:.1f}\n\n"
        f"*Teknik Skor: {puan}/130*\n"
        f"RSI: {v['rsi']:.1f} | Stoch K: {v['stoch_k']:.1f} | ADX: {v['adx']:.1f}\n"
        f"VWAP: {v['vwap']:.2f} | {'✅ Trend yukarı' if v['st_dir']==1 else '🔴 Trend aşağı'}\n\n"
        f"🎯 H1: {h1:.2f} | H2: {h2:.2f}\n"
        f"🛑 Stop: {stop:.2f} | ⚖️ R/Ö: 1/{ro:.1f}"
    )
    await update.message.reply_text(mesaj, parse_mode='Markdown')


async def detay_analiz(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("⚠️ Örnek: `/detay THYAO`", parse_mode='Markdown')
        return
    sembol = context.args[0].upper().replace(".IS", "")
    await update.message.reply_text(f"⏳ {sembol} detaylı analiz...")
    v = hisse_veri_cek(sembol)
    if not v:
        await update.message.reply_text(f"❌ {sembol} verisi alınamadı.")
        return
    puan, sin, stop, h1, h2, ro = puan_hesapla(v)
    skor_bar = "█" * (puan // 13) + "░" * (10 - puan // 13)
    etf_str = "".join(f"  • {n[:30]}: %{w:.3f}\n" for n, w in v['etf_top3'])
    mesaj = (
        f"🔬 *{sembol} — Detaylı Analiz*\n\n"
        f"*SKOR: {puan}/130*\n`[{skor_bar}]`\n\n"
        f"*📌 Sinyaller:*\n" + "\n".join(sin) + "\n\n"
        f"*💹 Fiyat:* {v['fiyat']:.2f} TL\n"
        f"🎯 H1: {h1:.2f} (+{((h1/v['fiyat'])-1)*100:.1f}%)\n"
        f"🎯 H2: {h2:.2f} (+{((h2/v['fiyat'])-1)*100:.1f}%)\n"
        f"🛑 Stop: {stop:.2f} (-{((1-(stop/v['fiyat']))*100):.1f}%)\n"
        f"⚖️ Risk/Ödül: 1/{ro:.1f}\n\n"
        f"*📊 İndikatörler:*\n"
        f"RSI(14): {v['rsi']:.1f} | MACD: {v['macd_hist']:.3f}\n"
        f"Stoch K/D: {v['stoch_k']:.1f}/{v['stoch_d']:.1f}\n"
        f"BB%: {v['bb_pct']:.2f} | ADX: {v['adx']:.1f}\n"
        f"VWAP: {v['vwap']:.2f} | ATR: {v['atr']:.2f}\n"
        + (f"\n*🌍 En Büyük ETF Sahipleri:*\n{etf_str}" if etf_str else "")
    )
    if len(mesaj) > 4000: mesaj = mesaj[:3990] + "\n..."
    await update.message.reply_text(mesaj, parse_mode='Markdown')


async def yildiz_tarama(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🔍 *Tarama başlatıldı...*\n_~60 saniye sürebilir_",
        parse_mode='Markdown'
    )
    sonuclar = []
    for sembol in HISSELER:
        v = hisse_veri_cek(sembol)
        if not v: continue
        puan, sin, stop, h1, h2, ro = puan_hesapla(v)
        if puan >= 60:
            sonuclar.append((puan, sembol, v['fiyat'], h1, stop, ro))
    sonuclar.sort(reverse=True)
    if not sonuclar:
        await update.message.reply_text("😴 Şu an güçlü sinyal yok.")
        return
    mesaj = "⭐ *EN GÜÇLÜ YÜKSELIŞ ADAYLARI* ⭐\n\n"
    for puan, sembol, fiyat, h1, stop, ro in sonuclar[:8]:
        yildiz = "⭐" * min(5, puan // 26)
        mesaj += f"{yildiz} *{sembol}* — {puan}/130\n💰 {fiyat:.2f} | 🎯 {h1:.2f} | 🛑 {stop:.2f} | R/Ö: 1/{ro:.1f}\n\n"
    if len(mesaj) > 4000: mesaj = mesaj[:3990] + "\n..."
    await update.message.reply_text(mesaj, parse_mode='Markdown')


async def top5(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("⏳ *Top 5 aranıyor...*", parse_mode='Markdown')
    sonuclar = []
    for sembol in HISSELER:
        v = hisse_veri_cek(sembol)
        if not v: continue
        puan, sin, stop, h1, h2, ro = puan_hesapla(v)
        sonuclar.append((puan, sembol, v, sin, stop, h1, h2, ro))
    sonuclar.sort(reverse=True)
    mesaj = "🏆 *GÜNÜN TOP 5 HİSSESİ*\n\n"
    for i, (puan, sembol, v, sin, stop, h1, h2, ro) in enumerate(sonuclar[:5], 1):
        yildiz = "⭐" * min(5, puan // 26)
        mesaj += (
            f"{i}. {yildiz} *{sembol}* — {puan}/130\n"
            f"💰 {v['fiyat']:.2f} | 🎯 {h1:.2f} | 🛑 {stop:.2f}\n"
            + "\n".join(sin[:3]) + "\n\n"
        )
    if len(mesaj) > 4000: mesaj = mesaj[:3990] + "\n..."
    await update.message.reply_text(mesaj, parse_mode='Markdown')


async def kisa_komut(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not piyasa_acik_mi():
        await update.message.reply_text(
            "🔴 *Piyasa kapalı!*\nHafta içi 10:00-18:00 arasında çalışır.",
            parse_mode='Markdown'
        )
        return
    await update.message.reply_text(
        "⚡ *Kısa Vade Taraması...*\n_VWAP + Supertrend + MACD (~60 saniye)_",
        parse_mode='Markdown'
    )
    sonuclar = []
    for sembol in HISSELER:
        v = hisse_veri_cek(sembol)
        if not v: continue
        puan, sin, stop, h1, h2, ro = puan_hesapla(v)
        if (puan >= 55 and v['fiyat'] > v['vwap'] > 0
                and v['st_dir'] == 1 and v['macd_hist'] > 0
                and 35 < v['rsi'] < 65):
            sonuclar.append((puan, sembol, v['fiyat'], h1, stop, ro, sin))
    sonuclar.sort(reverse=True)
    if not sonuclar:
        await update.message.reply_text("😴 Şu an 30dk yükseliş sinyali yok.")
        return
    mesaj = "⚡ *30 DAKİKA YÜKSELİŞ ADAYLARI* ⚡\n_(VWAP✅ Supertrend✅ MACD✅)_\n\n"
    for puan, sembol, fiyat, h1, stop, ro, sin in sonuclar[:6]:
        yildiz = "⭐" * min(5, puan // 26)
        mesaj += (
            f"{yildiz} *{sembol}* — {puan}/130\n"
            f"💰 {fiyat:.2f} | 🎯 {h1:.2f} | 🛑 {stop:.2f} | R/Ö: 1/{ro:.1f}\n"
            + "\n".join(sin[:2]) + "\n\n"
        )
    if len(mesaj) > 4000: mesaj = mesaj[:3990] + "\n..."
    await update.message.reply_text(mesaj, parse_mode='Markdown')


async def kisadetay_komut(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("⚠️ Örnek: `/kisadetay THYAO`", parse_mode='Markdown')
        return
    if not piyasa_acik_mi():
        await update.message.reply_text("🔴 Piyasa kapalı! 10:00-18:00 arası çalışır.")
        return
    sembol = context.args[0].upper().replace(".IS", "")
    await update.message.reply_text(f"⚡ {sembol} kısa vade analiz...")
    v = hisse_veri_cek(sembol)
    if not v:
        await update.message.reply_text(f"❌ {sembol} verisi alınamadı.")
        return
    puan, sin, stop, h1, h2, ro = puan_hesapla(v)
    skor_bar = "█" * (puan // 13) + "░" * (10 - puan // 13)
    mesaj = (
        f"⚡ *{sembol} — Kısa Vade*\n\n"
        f"*SKOR: {puan}/130*\n`[{skor_bar}]`\n\n"
        f"💰 Fiyat: {v['fiyat']:.2f} | VWAP: {v['vwap']:.2f}\n"
        f"{'✅ Fiyat VWAP üzerinde' if v['fiyat'] > v['vwap'] else '🔴 Fiyat VWAP altında'}\n"
        f"{'✅ Supertrend yukarı' if v['st_dir']==1 else '🔴 Supertrend aşağı'}\n"
        f"RSI: {v['rsi']:.1f} | MACD hist: {v['macd_hist']:.3f}\n\n"
        f"🎯 H1: {h1:.2f} (+{((h1/v['fiyat'])-1)*100:.1f}%)\n"
        f"🎯 H2: {h2:.2f} (+{((h2/v['fiyat'])-1)*100:.1f}%)\n"
        f"🛑 Stop: {stop:.2f} (-{((1-(stop/v['fiyat']))*100):.1f}%)\n"
        f"⚖️ Risk/Ödül: 1/{ro:.1f}\n\n"
        f"*📌 Sinyaller:*\n" + "\n".join(sin)
    )
    if len(mesaj) > 4000: mesaj = mesaj[:3990] + "\n..."
    await update.message.reply_text(mesaj, parse_mode='Markdown')


async def etf_komut(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("⚠️ Örnek: `/etf THYAO`", parse_mode='Markdown')
        return
    sembol = context.args[0].upper().replace(".IS", "")
    await update.message.reply_text(f"⏳ {sembol} ETF sahiplik verisi çekiliyor...")
    try:
        h   = bp.Ticker(sembol)
        etf = h.etf_holders
        if etf.empty:
            await update.message.reply_text(f"❌ {sembol} için ETF verisi yok.")
            return
        toplam = etf['holding_weight_pct'].sum()
        top10  = etf.nlargest(10, 'holding_weight_pct')[['name','holding_weight_pct','aum_usd']]
        mesaj  = f"🌍 *{sembol} — ETF Sahiplik*\n\n{len(etf)} ETF | Toplam ağırlık: %{toplam:.3f}\n\n*En Büyük 10:*\n"
        for _, row in top10.iterrows():
            mesaj += f"  • {str(row['name'])[:35]}\n    %{row['holding_weight_pct']:.3f} | AUM: {para_fmt(row['aum_usd'])}\n"
        await update.message.reply_text(mesaj, parse_mode='Markdown')
    except Exception as e:
        await update.message.reply_text(f"❌ ETF verisi alınamadı: {e}")


async def kurumsal_tarama(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🌍 *Kurumsal ETF Taraması...*\n_~90 saniye sürebilir_",
        parse_mode='Markdown'
    )
    sonuclar = []
    for sembol in HISSELER:
        v = hisse_veri_cek(sembol)
        if not v or v['etf_toplam'] < 0.1: continue
        puan, _, stop, h1, h2, ro = puan_hesapla(v)
        sonuclar.append((v['etf_toplam'], puan, sembol, v['fiyat'], h1, stop, v['etf_sayisi']))
    sonuclar.sort(reverse=True)
    if not sonuclar:
        await update.message.reply_text("😴 ETF sahiplik verisi bulunamadı.")
        return
    mesaj = "🏦 *EN YÜKSEK ETF SAHİPLİĞİ OLAN HİSSELER*\n\n"
    for et, puan, sembol, fiyat, h1, stop, sayisi in sonuclar[:10]:
        mesaj += (
            f"*{sembol}* — %{et:.3f} ({sayisi} ETF) | Teknik: {puan}/130\n"
            f"  💰 {fiyat:.2f} | 🎯 {h1:.2f} | 🛑 {stop:.2f}\n\n"
        )
    if len(mesaj) > 4000: mesaj = mesaj[:3990] + "\n..."
    await update.message.reply_text(mesaj, parse_mode='Markdown')


async def yabanci_komut(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("⚠️ Örnek: `/yabanci THYAO`", parse_mode='Markdown')
        return
    sembol = context.args[0].upper().replace(".IS", "")
    await update.message.reply_text(f"⏳ {sembol} yabancı yatırımcı verisi...")
    v = hisse_veri_cek(sembol)
    if not v:
        await update.message.reply_text(f"❌ {sembol} verisi alınamadı.")
        return
    if   v['foreign_r'] >= 50: yorum = "🌍 Çok yüksek yabancı ilgisi"
    elif v['foreign_r'] >= 30: yorum = "🟡 Yüksek yabancı ilgisi"
    elif v['foreign_r'] >= 10: yorum = "⚪ Orta yabancı ilgisi"
    else:                       yorum = "🔴 Düşük yabancı ilgisi"
    etf_str = "".join(f"  • {n[:35]}: %{w:.3f}\n" for n, w in v['etf_top3'])
    mesaj = (
        f"🌍 *{sembol} — Yabancı Yatırımcı*\n\n*{yorum}*\n\n"
        f"👥 Yabancı Oranı: %{v['foreign_r']:.1f}\n"
        f"📊 Halka Açıklık: %{v['free_float']:.1f}\n"
        f"📈 F/K: {v['pe_ratio']:.1f} | F/DD: {v['pb_ratio']:.1f}\n"
        f"💼 Piyasa Değeri: {para_fmt(v['market_cap'])}\n\n"
        f"🌍 {v['etf_sayisi']} ETF tutuyor | Toplam ağırlık: %{v['etf_toplam']:.3f}\n"
        + (f"*En Büyük ETF'ler:*\n{etf_str}" if etf_str else "")
    )
    await update.message.reply_text(mesaj, parse_mode='Markdown')


async def combo_komut(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("⚠️ Örnek: `/combo THYAO`", parse_mode='Markdown')
        return
    sembol = context.args[0].upper().replace(".IS", "")
    await update.message.reply_text(f"🔀 {sembol} combo analiz...")
    v = hisse_veri_cek(sembol)
    if not v:
        await update.message.reply_text(f"❌ {sembol} verisi alınamadı.")
        return
    puan, sin, stop, h1, h2, ro = puan_hesapla(v)
    if   puan >= 100: karar = "🚀 ÇOK GÜÇLÜ FIRSAT!"
    elif puan >= 80:  karar = "⭐ GÜÇLÜ SİNYAL"
    elif puan >= 60:  karar = "🟡 ORTA KUVVETLİ"
    else:             karar = "⚪ Zayıf sinyal"
    skor_bar = "█" * (puan // 13) + "░" * (10 - puan // 13)
    mesaj = (
        f"🔀 *{sembol} — COMBO ANALİZ*\n\n"
        f"*{karar}*\nSkor: {puan}/130\n`[{skor_bar}]`\n\n"
        f"💰 {v['fiyat']:.2f} TL\n"
        f"🎯 H1: {h1:.2f} (+{((h1/v['fiyat'])-1)*100:.1f}%) | H2: {h2:.2f}\n"
        f"🛑 Stop: {stop:.2f} | ⚖️ R/Ö: 1/{ro:.1f}\n\n"
        f"*📌 Sinyaller:*\n" + "\n".join(sin) + "\n\n"
        f"*🌍 Kurumsal:*\n"
        f"Yabancı: %{v['foreign_r']:.1f} | ETF: {v['etf_sayisi']} adet (%{v['etf_toplam']:.3f})\n"
    )
    if len(mesaj) > 4000: mesaj = mesaj[:3990] + "\n..."
    await update.message.reply_text(mesaj, parse_mode='Markdown')




async def yardim(update: Update, context: ContextTypes.DEFAULT_TYPE):
    mesaj = (
        "🤖 *BIST ANALİZ BOTU — KOMUT LİSTESİ*\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        "📊 *FİYAT ve ANALİZ*\n"
        "`/fiyat THYAO` — Anlık fiyat + özet\n"
        "`/detay THYAO` — Tam teknik rapor + hedef/stop\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        "🔍 *TARAMA*\n"
        "`/yildiz` — En güçlü yükseliş adayları (tüm hisseler)\n"
        "`/top5` — Günün en iyi 5 hissesi\n"
        "`/kisa` — 30dk yükseliş adayları _(piyasa saatinde)_\n"
        "`/kisadetay THYAO` — Tek hisse kısa vade analizi\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        "🌍 *KURUMSAL ve YABANCI*\n"
        "`/etf THYAO` — Hangi büyük ETF'ler tutuyor?\n"
        "`/kurumsal` — ETF ağırlığı en yüksek hisseler\n"
        "`/yabanci THYAO` — Yabancı oranı + F/K + ETF\n"
        "`/combo THYAO` — Teknik + Kurumsal combo skor\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        "❓ *SKOR SİSTEMİ*\n"
        "Maksimum 130 puan\n"
        "🚀 100+ Çok güçlü fırsat\n"
        "⭐ 80-99 Güçlü sinyal\n"
        "🟡 60-79 Orta kuvvetli\n"
        "⚪ 60 altı Zayıf sinyal\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        "⏰ *Piyasa saati:* Hafta içi 10:00-18:00\n"
        "/yardim — Bu menüyü göster"
    )
    await update.message.reply_text(mesaj, parse_mode='Markdown')
# ── OTOMATİK GÖREVLER ────────────────────────────────────────
async def otomatik_tarama(context: ContextTypes.DEFAULT_TYPE):
    try:
        for sembol in HISSELER:
            v = hisse_veri_cek(sembol)
            if not v: continue
            puan, sin, stop, h1, h2, ro = puan_hesapla(v)
            if puan >= 80:
                yildiz = "⭐" * min(5, puan // 26)
                mesaj = (
                    f"🚨 *OTOMATİK ALARM: {sembol}*\n"
                    f"{yildiz} Skor: {puan}/130\n"
                    f"💰 {v['fiyat']:.2f} | 🎯 {h1:.2f} | 🛑 {stop:.2f}\n"
                    + "\n".join(sin[:4])
                )
                await context.bot.send_message(chat_id=CHAT_ID, text=mesaj, parse_mode='Markdown')
    except Exception as e:
        print(f"Otomatik tarama hatası: {e}")


async def kisa_otomatik(context: ContextTypes.DEFAULT_TYPE):
    if not piyasa_acik_mi():
        return
    try:
        for sembol in HISSELER:
            v = hisse_veri_cek(sembol)
            if not v: continue
            puan, sin, stop, h1, h2, ro = puan_hesapla(v)
            if (puan >= 70 and v['fiyat'] > v['vwap'] > 0
                    and v['st_dir'] == 1 and v['macd_hist'] > 0
                    and 35 < v['rsi'] < 65):
                mesaj = (
                    f"⚡ *KISA VADE ALARM: {sembol}*\n"
                    f"Skor: {puan}/130\n"
                    f"💰 {v['fiyat']:.2f} | VWAP: {v['vwap']:.2f}\n"
                    f"🎯 {h1:.2f} | 🛑 {stop:.2f} | R/Ö: 1/{ro:.1f}\n"
                    + "\n".join(sin[:3])
                )
                await context.bot.send_message(chat_id=CHAT_ID, text=mesaj, parse_mode='Markdown')
    except Exception as e:
        print(f"Kısa vade alarm hatası: {e}")


# ── BAŞLAT ───────────────────────────────────────────────────
def main():
    print("🤖 BIST Analiz Botu (borsapy tabanlı) Başlatılıyor...")
    app = Application.builder().token(TOKEN).build()

    app.add_handler(CommandHandler("fiyat",     fiyat_sorgula))
    app.add_handler(CommandHandler("detay",     detay_analiz))
    app.add_handler(CommandHandler("yildiz",    yildiz_tarama))
    app.add_handler(CommandHandler("top5",      top5))
    app.add_handler(CommandHandler("kisa",      kisa_komut))
    app.add_handler(CommandHandler("kisadetay", kisadetay_komut))
    app.add_handler(CommandHandler("etf",       etf_komut))
    app.add_handler(CommandHandler("kurumsal",  kurumsal_tarama))
    app.add_handler(CommandHandler("yabanci",   yabanci_komut))
    app.add_handler(CommandHandler("combo",     combo_komut))
    app.add_handler(CommandHandler("yardim",    yardim))

    # app.job_queue.run_repeating(otomatik_tarama, interval=900, first=15)
    # app.job_queue.run_repeating(kisa_otomatik,   interval=900, first=30)

    print("✅ Bot hazır!")
    print("📌 Fiyat   : /fiyat /detay")
    print("📌 Tarama  : /yildiz /top5 /kisa /kisadetay")
    print("📌 Kurumsal: /etf /kurumsal /yabanci /combo")
    print("📌 Yardım  : /yardim")
    app.run_polling()


# ── HAFTA SONU UYKU MANTIĞI ──────────────────────────────────
# Railway ücretsiz 500 saat/ay limiti için hafta sonu bot uyur.
# Hafta içi 5×24 = 120 saat → ayda ~480 saat → limit içinde kalır.

import time
import datetime as dt

def calis():
    while True:
        simdi = datetime.now(ISTANBUL_TZ)
        if simdi.weekday() >= 5:  # Cumartesi veya Pazar
            # Pazartesi 09:55'e kadar bekle
            gun_kaldi = 7 - simdi.weekday()
            pzt = (simdi + dt.timedelta(days=gun_kaldi)).replace(
                hour=9, minute=55, second=0, microsecond=0
            )
            bekle = (pzt - simdi).total_seconds()
            print(f"😴 Hafta sonu — Pazartesi 09:55'e kadar bekleniyor ({bekle/3600:.1f} saat)")
            time.sleep(max(bekle, 60))
        else:
            print("📅 Hafta içi — Bot başlatılıyor...")
            main()
            # main() biterse (hata vs.) 30 sn bekle tekrar dene
            time.sleep(30)

if __name__ == "__main__":
    calis()
