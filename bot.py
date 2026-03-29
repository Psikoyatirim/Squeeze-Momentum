import warnings
warnings.filterwarnings("ignore")

import pandas as pd
import numpy as np
from tvDatafeed import TvDatafeed, Interval
from tradingview_screener import get_all_symbols
import requests
import time
import os
from datetime import datetime

# =====================
# TELEGRAM AYARLARI
# =====================
BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN', '8035211094:AAEqHt4ZosBJsuT1FxdCcTR9p9uJ1O073zY')
CHAT_ID = os.getenv('TELEGRAM_CHAT_ID', '-1002715468798')

def telegram_gonder(mesaj):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    try:
        r = requests.post(url, data={"chat_id": CHAT_ID, "text": mesaj, "parse_mode": "HTML"}, timeout=15)
        if r.status_code == 200:
            print("📤 Telegram gönderildi", flush=True)
        else:
            print(f"⚠️ Telegram hatası: {r.status_code}", flush=True)
    except Exception as e:
        print(f"⚠️ Telegram bağlantı hatası: {e}", flush=True)

def telegram_parcali(baslik, satirlar, parca_basina=30):
    if not satirlar:
        return
    toplam = (len(satirlar) + parca_basina - 1) // parca_basina
    for i in range(0, len(satirlar), parca_basina):
        parca = satirlar[i:i + parca_basina]
        no = (i // parca_basina) + 1
        ek = f" ({no}/{toplam})" if toplam > 1 else ""
        msg = f"{baslik}{ek}\n\n" + "\n".join(parca)
        telegram_gonder(msg)
        time.sleep(0.5)

# =====================
# SUNUCU AYARLARI (SABİT)
# =====================
INTERVAL = Interval.in_1_hour
INTERVAL_ADI = "1 Saat"
N_BARS = 100
SCAN_INTERVAL_SECONDS = 7200  # 2 saat

# =====================
# SQUEEZE MOMENTUM HESAPLAMA
# =====================
def sma(series, length):
    return series.rolling(window=length).mean()

def stdev(series, length):
    return series.rolling(window=length).std()

def SqueezeMomentum(data, mult=2, length=20, multKC=1.5, lengthKC=20):
    df = data.copy()
    df['basis'] = sma(df['Close'], length)
    df['dev'] = multKC * stdev(df['Close'], length)
    df['upperBB'] = df['basis'] + df['dev']
    df['lowerBB'] = df['basis'] - df['dev']
    df['ma'] = sma(df['Close'], lengthKC)
    df['tr0'] = abs(df["High"] - df["Low"])
    df['tr1'] = abs(df["High"] - df["Close"].shift())
    df['tr2'] = abs(df["Low"] - df["Close"].shift())
    df['range'] = df[['tr0', 'tr1', 'tr2']].max(axis=1)
    df['rangema'] = sma(df['range'], lengthKC)
    df['upperKC'] = df['ma'] + df['rangema'] * multKC
    df['lowerKC'] = df['ma'] - df['rangema'] * multKC
    df['Squeeze'] = (df['lowerBB'] < df['lowerKC']) & (df['upperBB'] > df['upperKC'])
    return df

# =====================
# TARAMA
# =====================
def tarama_yap(tv, scan_number=1):
    signals = []
    toplam_hisse = 0

    print(f"\n{'='*50}", flush=True)
    print(f"🔍 TARAMA #{scan_number} — {datetime.now().strftime('%d.%m.%Y %H:%M:%S')}", flush=True)
    print(f"{'='*50}", flush=True)

    try:
        hisseler = get_all_symbols(market='turkey')
        hisseler = [s.replace('BIST:', '') for s in hisseler]
        hisseler = sorted(hisseler)
        toplam_hisse = len(hisseler)
        print(f"📊 {toplam_hisse} hisse taranacak", flush=True)
    except Exception as e:
        print(f"❌ Hisse listesi alınamadı: {e}", flush=True)
        return signals

    for i, hisse in enumerate(hisseler, 1):
        if i % 50 == 1:
            print(f"📈 [{i}/{toplam_hisse}] İşleniyor...", flush=True)

        try:
            data = tv.get_hist(symbol=hisse, exchange='BIST', interval=INTERVAL, n_bars=N_BARS)
            if data is None or len(data) < 25:
                continue

            data.rename(columns={
                'open': 'Open', 'high': 'High',
                'low': 'Low', 'close': 'Close', 'volume': 'Volume'
            }, inplace=True)
            data = data.reset_index()

            sq = SqueezeMomentum(data)
            sq['datetime'] = pd.to_datetime(sq['datetime'])
            sq.set_index('datetime', inplace=True)

            tail = sq.tail(2).reset_index()
            if len(tail) < 2:
                continue

            # Squeeze sinyali: önceki bar False, son bar True
            sq_signal = (tail.loc[0, 'Squeeze'] == False) and (tail.loc[1, 'Squeeze'] == True)

            if sq_signal:
                fiyat = round(float(tail.loc[1, 'Close']), 2)
                signals.append({
                    "hisse": hisse,
                    "fiyat": fiyat
                })
                print(f"  🚨 SİNYAL: {hisse} — {fiyat} TL", flush=True)

        except Exception:
            continue

        time.sleep(0.3)

    print(f"✅ Tamamlandı! {len(signals)} sinyal bulundu.", flush=True)
    return signals


# =====================
# ANA DÖNGÜ
# =====================
if __name__ == "__main__":
    print("🚀 Squeeze Momentum Otomatik Tarayıcı Başladı", flush=True)
    print(f"📈 Interval: {INTERVAL_ADI} | Her 2 saatte bir", flush=True)

    tv = TvDatafeed()

    telegram_gonder(
        f"🤖 <b>Squeeze Momentum Bot Aktif</b>\n"
        f"📅 {datetime.now().strftime('%d.%m.%Y %H:%M:%S')}\n"
        f"⏰ Interval: {INTERVAL_ADI}\n"
        f"🔄 Her 2 saatte bir tarama yapılacak"
    )

    scan_count = 0
    while True:
        scan_count += 1
        simdi = datetime.now().strftime('%d.%m.%Y %H:%M:%S')

        try:
            signals = tarama_yap(tv, scan_number=scan_count)

            if signals:
                telegram_gonder(
                    f"🚨 <b>Squeeze Momentum — #{scan_count}</b>\n"
                    f"📅 {simdi}\n"
                    f"⏰ {INTERVAL_ADI}\n\n"
                    f"✅ Sinyal: {len(signals)} hisse"
                )
                time.sleep(0.5)

                satirlar = [
                    f"<b>{s['hisse']}</b> — {s['fiyat']} TL"
                    for s in signals
                ]
                telegram_parcali("📈 <b>SQUEEZE SİNYALLERİ</b>", satirlar)

            else:
                telegram_gonder(
                    f"📊 <b>Squeeze Momentum — #{scan_count}</b>\n"
                    f"📅 {simdi}\n"
                    f"⏰ {INTERVAL_ADI}\n\n"
                    f"❌ Sinyal bulunamadı\n"
                    f"⏳ Sonraki tarama 2 saat sonra..."
                )

        except Exception as e:
            print(f"❌ Tarama hatası: {e}", flush=True)
            telegram_gonder(f"⚠️ Tarama hatası: {str(e)[:100]}\n🔄 30 saniye sonra yeniden deneniyor...")
            time.sleep(30)
            continue

        print(f"\n⏳ 2 saat bekleniyor...", flush=True)
        time.sleep(SCAN_INTERVAL_SECONDS)
