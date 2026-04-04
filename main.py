from openai import OpenAI
import requests
from dotenv import load_dotenv
import os
import pandas as pd
import ta
import openpyxl
from datetime import datetime
from plyer import notification
import schedule
import time
import threading

# Load API key dari file .env
load_dotenv()
client = OpenAI(
    api_key=os.getenv("OPENROUTER_API_KEY"),
    base_url="https://openrouter.ai/api/v1"
)
CRYPTOPANIC_TOKEN = os.getenv("CRYPTOPANIC_TOKEN")
NEWS_API_KEY = os.getenv("NEWS_API_KEY")
MARKETAUX_API_KEY = os.getenv("MARKETAUX_API_KEY")

# ==============================
# FUNGSI AMBIL DATA CRYPTO
# ==============================
def get_crypto_price(nama_crypto):
    url = "https://api.coingecko.com/api/v3/simple/price"
    params = {
        "ids": nama_crypto,
        "vs_currencies": "idr,usd",
        "include_24hr_change": "true"
    }
    response = requests.get(url, params=params)
    return response.json()

# ==============================
# FUNGSI AMBIL DATA SAHAM
# ==============================
def get_stock_price(kode_saham):
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{kode_saham}"
    headers = {"User-Agent": "Mozilla/5.0"}
    response = requests.get(url, headers=headers)
    data = response.json()
    price = data["chart"]["result"][0]["meta"]["regularMarketPrice"]
    currency = data["chart"]["result"][0]["meta"]["currency"]
    return {"harga": price, "mata_uang": currency, "kode": kode_saham}

# ==============================
# FUNGSI AMBIL BERITA CRYPTO
# ==============================
def get_crypto_news(nama_crypto):
    url = "https://newsapi.org/v2/everything"
    params = {
        "q": nama_crypto,
        "apiKey": NEWS_API_KEY,
        "language": "en",
        "sortBy": "publishedAt",
        "pageSize": 5
    }
    try:
        response = requests.get(url, params=params)
        data = response.json()
        berita = []
        for item in data.get("articles", [])[:5]:
            berita.append({
                "judul": item["title"],
                "sumber": item["source"]["name"]
            })
        return berita
    except:
        return []
    
# ==============================
# FUNGSI BERITA MARKETAUX
# ==============================
def get_marketaux_news(simbol):
    url = "https://api.marketaux.com/v1/news/all"
    params = {
        "symbols": simbol,
        "api_token": MARKETAUX_API_KEY,
        "limit": 3,
        "language": "en"
    }
    try:
        response = requests.get(url, params=params)
        data = response.json()
        berita = []
        for item in data.get("data", [])[:3]:
            berita.append({
                "judul": item["title"],
                "sumber": item.get("source", "Unknown")
            })
        return berita
    except:
        return []

# ==============================
# FUNGSI AMBIL BERITA SAHAM
# ==============================
def get_stock_news(kode_saham):
    nama_map = {
    "BBRI.JK": "Bank Rakyat Indonesia BRI saham",
    "BBCA.JK": "Bank Central Asia",
    "TLKM.JK": "Telkom Indonesia saham",
    "GOTO.JK": "GoTo Gojek Tokopedia saham",
    "BBNI.JK": "Bank Negara Indonesia BNI saham",
    "BMRI.JK": "Bank Mandiri saham",
    "ASII.JK": "Astra International saham",
    "UNVR.JK": "Unilever Indonesia saham",
    "AAPL": "Apple stock",
    "TSLA": "Tesla stock",
    "NVDA": "Nvidia stock",
    "GOOGL": "Google Alphabet stock",
    "MSFT": "Microsoft stock",
    "AMZN": "Amazon stock"
}
    
    keyword = nama_map.get(kode_saham, kode_saham)
    
    # Ambil dari NewsAPI
    url = "https://newsapi.org/v2/everything"
    params = {
        "q": f'"{keyword}"',
        "apiKey": NEWS_API_KEY,
        "language": "en",
        "sortBy": "publishedAt",
        "pageSize": 3
    }
    berita = []
    try:
        response = requests.get(url, params=params)
        data = response.json()
        for item in data.get("articles", [])[:3]:
            berita.append({
                "judul": item["title"],
                "sumber": item["source"]["name"]
            })
    except:
        pass
    
    # Untuk saham Indonesia, skip Marketaux karena tidak relevan
    if not kode_saham.endswith(".JK"):
        marketaux_berita = get_marketaux_news(kode_saham)
        berita.extend(marketaux_berita)
    
    return berita[:5]  # Maksimal 5 berita

# ==============================
# FUNGSI INDIKATOR TEKNIKAL CRYPTO
# ==============================
def get_crypto_indicators(nama_crypto):
    try:
        url = f"https://api.coingecko.com/api/v3/coins/{nama_crypto}/market_chart"
        params = {"vs_currency": "usd", "days": "30", "interval": "daily"}
        response = requests.get(url, params=params)
        data = response.json()
        
        harga = [x[1] for x in data["prices"]]
        df = pd.DataFrame(harga, columns=["close"])
        
        # Hitung RSI
        df["rsi"] = ta.momentum.RSIIndicator(df["close"], window=14).rsi()
        
        # Hitung MACD
        macd = ta.trend.MACD(df["close"])
        df["macd"] = macd.macd()
        df["macd_signal"] = macd.macd_signal()
        
        rsi = round(df["rsi"].iloc[-1], 2)
        macd_val = round(df["macd"].iloc[-1], 4)
        macd_sig = round(df["macd_signal"].iloc[-1], 4)
        
        # Interpretasi RSI
        if rsi < 30:
            rsi_status = "OVERSOLD (potensi BELI)"
        elif rsi > 70:
            rsi_status = "OVERBOUGHT (potensi JUAL)"
        else:
            rsi_status = "NORMAL"
        
        # Interpretasi MACD
        if macd_val > macd_sig:
            macd_status = "BULLISH (tren naik)"
        else:
            macd_status = "BEARISH (tren turun)"
        
        return {
            "rsi": rsi,
            "rsi_status": rsi_status,
            "macd": macd_val,
            "macd_signal": macd_sig,
            "macd_status": macd_status
        }
    except:
        return None

# ==============================
# FUNGSI INDIKATOR TEKNIKAL SAHAM
# ==============================
def get_stock_indicators(kode_saham):
    try:
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{kode_saham}"
        params = {"interval": "1d", "range": "3mo"}
        headers = {"User-Agent": "Mozilla/5.0"}
        response = requests.get(url, params=params, headers=headers)
        data = response.json()
        
        harga = data["chart"]["result"][0]["indicators"]["quote"][0]["close"]
        harga = [x for x in harga if x is not None]
        df = pd.DataFrame(harga, columns=["close"])
        
        # Hitung RSI
        df["rsi"] = ta.momentum.RSIIndicator(df["close"], window=14).rsi()
        
        # Hitung MACD
        macd = ta.trend.MACD(df["close"])
        df["macd"] = macd.macd()
        df["macd_signal"] = macd.macd_signal()
        
        rsi = round(df["rsi"].iloc[-1], 2)
        macd_val = round(df["macd"].iloc[-1], 4)
        macd_sig = round(df["macd_signal"].iloc[-1], 4)
        
        # Interpretasi RSI
        if rsi < 30:
            rsi_status = "OVERSOLD (potensi BELI)"
        elif rsi > 70:
            rsi_status = "OVERBOUGHT (potensi JUAL)"
        else:
            rsi_status = "NORMAL"
        
        # Interpretasi MACD
        if macd_val > macd_sig:
            macd_status = "BULLISH (tren naik)"
        else:
            macd_status = "BEARISH (tren turun)"
        
        return {
            "rsi": rsi,
            "rsi_status": rsi_status,
            "macd": macd_val,
            "macd_signal": macd_sig,
            "macd_status": macd_status
        }
    except:
        return None

# ==============================
# FUNGSI ANALISIS GROQ AI
# ==============================
def analisis_ai(pertanyaan, data_harga, berita, indikator):
    prompt = f"""
    Kamu adalah asisten investasi profesional yang membantu investor Indonesia.
    
    Data harga saat ini:
    {data_harga}
    
    Indikator Teknikal:
    {indikator}
    
    Berita terkini:
    {berita}
    
    Pertanyaan pengguna: {pertanyaan}
    
    Berikan analisis yang:
    1. Jelas dan mudah dipahami pemula
    2. Jelaskan kondisi RSI dan MACD dengan bahasa sederhana
    3. Hubungkan berita terkini dengan indikator teknikal
    4. Sertakan sinyal: BELI / JUAL / HOLD
    5. Sentimen pasar: POSITIF / NEGATIF / NETRAL
    6. Jelaskan alasannya secara singkat
    7. Ingatkan bahwa investasi selalu ada risikonya
    
    Jawab dalam Bahasa Indonesia.
    """
    
    response = client.chat.completions.create(
        model="meta-llama/llama-3.3-70b-instruct",
        max_tokens=1500,
        messages=[{"role": "user", "content": prompt}]
    )
    return response.choices[0].message.content

# ==============================
# MENU UTAMA
# ==============================

# ==============================
# FUNGSI SIMPAN KE EXCEL
# ==============================
def simpan_ke_excel(jenis, nama_aset, harga_data, sinyal, analisis):
    nama_file = "histori_analisis.xlsx"
    
    # Cek apakah file sudah ada
    if os.path.exists(nama_file):
        wb = openpyxl.load_workbook(nama_file)
        ws = wb.active
    else:
        # Buat file baru dengan header
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Histori Analisis"
        ws.append([
            "Tanggal & Waktu",
            "Jenis",
            "Nama Aset",
            "Harga (IDR/USD)",
            "Perubahan 24 Jam",
            "Sinyal AI",
            "Analisis Lengkap"
        ])
        # Style header
        from openpyxl.styles import Font, PatternFill
        for cell in ws[1]:
            cell.font = Font(bold=True, color="FFFFFF")
            cell.fill = PatternFill("solid", fgColor="1F4E79")
    
    # Ambil data harga
    try:
        if jenis == "Crypto":
            aset_key = list(harga_data.keys())[0]
            harga = f"IDR {harga_data[aset_key].get('idr', '-'):,} | USD {harga_data[aset_key].get('usd', '-'):,}"
            perubahan = f"{harga_data[aset_key].get('idr_24h_change', 0):.2f}%"
        else:
            harga = f"{harga_data.get('mata_uang', '')} {harga_data.get('harga', '-')}"
            perubahan = "-"
    except:
        harga = "-"
        perubahan = "-"
    
    # Tentukan sinyal dari teks analisis
    sinyal_detected = "HOLD"
    if "BELI" in analisis.upper():
        sinyal_detected = "BELI"
    elif "JUAL" in analisis.upper():
        sinyal_detected = "JUAL"
    
    # Tambah baris baru
    ws.append([
        datetime.now().strftime("%d/%m/%Y %H:%M"),
        jenis,
        nama_aset.upper(),
        harga,
        perubahan,
        sinyal_detected,
        analisis[:500]  # Simpan 500 karakter pertama
    ])
    
    # Auto-width kolom
    for col in ws.columns:
        max_length = max(len(str(cell.value or "")) for cell in col)
        ws.column_dimensions[col[0].column_letter].width = min(max_length + 2, 50)
    
    wb.save(nama_file)
    print(f"✅ Analisis tersimpan ke {nama_file}!")

# ==============================
# FUNGSI ALERT HARGA
# ==============================
alert_list = []  # Simpan daftar alert

# ==============================
# FUNGSI SIMPAN & LOAD ALERT
# ==============================
ALERT_FILE = "alerts.json"

def simpan_alert():
    import json
    with open(ALERT_FILE, "w") as f:
        json.dump(alert_list, f)

def load_alert():
    import json
    global alert_list
    if os.path.exists(ALERT_FILE):
        with open(ALERT_FILE, "r") as f:
            alert_list = json.load(f)
        if alert_list:
            print(f"✅ {len(alert_list)} alert dimuat dari file!")

def tambah_alert(jenis, nama_aset, harga_target, kondisi):
    alert_list.append({
        "jenis": jenis,
        "nama_aset": nama_aset,
        "harga_target": harga_target,
        "kondisi": kondisi
    })
    simpan_alert()
    print(f"✅ Alert ditambahkan: {nama_aset} {kondisi} {harga_target}")

def cek_alert():
    for alert in alert_list[:]:
        try:
            if alert["jenis"] == "crypto":
                data = get_crypto_price(alert["nama_aset"])
                aset_key = list(data.keys())[0]
                harga_sekarang = data[aset_key]["usd"]
            else:
                data = get_stock_price(alert["nama_aset"])
                harga_sekarang = data["harga"]

            terpicu = False
            if alert["kondisi"] == "naik" and harga_sekarang >= alert["harga_target"]:
                terpicu = True
            elif alert["kondisi"] == "turun" and harga_sekarang <= alert["harga_target"]:
                terpicu = True

            if terpicu:
                pesan = f"{alert['nama_aset']} sudah {alert['kondisi']} ke {harga_sekarang}!"
                print(f"\n🔔 ALERT: {pesan}")
                notification.notify(
                    title="🚨 CRYPTO & SAHAM ALERT!",
                    message=pesan,
                    timeout=10
                )
                alert_list.remove(alert)
                simpan_alert()

        except:
            pass

def jalankan_monitor():
    schedule.every(1).minutes.do(cek_alert)
    while True:
        schedule.run_pending()
        time.sleep(1)

def main():
    print("=" * 55)
    print("   CRYPTO & SAHAM AGENT - Powered by OpenRouter AI")
    print("   + Berita & Sentimen Pasar Real-time")
    print("=" * 55)

    load_alert()
    
    # Jalankan monitor kalau ada alert tersimpan
    if alert_list:
        t = threading.Thread(target=jalankan_monitor, daemon=True)
        t.start()
        print("🔄 Monitor harga berjalan di background!")
    
    while True:
        print("\nPilih menu:")
        print("1. Cek harga & analisis Crypto")
        print("2. Cek harga & analisis Saham")
        print("3. Set Alert Harga")
        print("4. Lihat Alert Aktif")
        print("5. Hapus Alert")
        print("6. Keluar")

        pilihan = input("\nMasukkan pilihan (1/2/3/4/5/6): ")

        if pilihan == "1":
            print("\nContoh: bitcoin, ethereum, solana, dogecoin")
            crypto = input("Masukkan nama crypto: ").lower()
            print(f"\n⏳ Mengambil data harga {crypto}...")
            data_harga = get_crypto_price(crypto)
            
            if not data_harga:
                print("❌ Crypto tidak ditemukan!")
                continue
            
            print(f"✅ Data harga berhasil diambil!")
            print(f"⏳ Mengambil berita terkini {crypto}...")
            berita = get_crypto_news(crypto)
            
            if berita:
                print(f"✅ {len(berita)} berita ditemukan!")
                print("\n📰 Berita Terkini:")
                for i, b in enumerate(berita, 1):
                    print(f"  {i}. {b['judul']}")
            else:
                print("⚠️ Tidak ada berita terkini.")

            pertanyaan = input("\nAda pertanyaan? (atau tekan Enter untuk analisis umum): ")
            if not pertanyaan:
                pertanyaan = f"Berikan analisis lengkap untuk {crypto}"
            
            print(f"⏳ Menghitung indikator teknikal {crypto}...")
            indikator = get_crypto_indicators(crypto)
            if indikator:
                print(f"✅ Indikator berhasil dihitung!")
                print(f"   📈 RSI: {indikator['rsi']} → {indikator['rsi_status']}")
                print(f"   📉 MACD: {indikator['macd_status']}")
            else:
                print("⚠️ Indikator tidak tersedia.")

            print("\n🤖 Groq AI sedang menganalisis...\n")
            hasil = analisis_ai(pertanyaan, data_harga, berita, indikator)
            print("-" * 55)
            print(hasil)
            print("-" * 55)
            simpan_ke_excel("Crypto", crypto, data_harga, "", hasil)
            
        elif pilihan == "2":
            print("\nContoh saham Indonesia: BBCA.JK, GOTO.JK, TLKM.JK, BBRI.JK")
            print("Contoh saham US: AAPL, TSLA, NVDA, GOOGL")
            saham = input("Masukkan kode saham: ").upper()
            print(f"\n⏳ Mengambil data harga {saham}...")
            
            try:
                data_harga = get_stock_price(saham)
                print(f"✅ Data harga berhasil diambil!")
                print(f"⏳ Mengambil berita terkini {saham}...")
                berita = get_stock_news(saham)
                
                if berita:
                    print(f"✅ {len(berita)} berita ditemukan!")
                    print("\n📰 Berita Terkini:")
                    for i, b in enumerate(berita, 1):
                        print(f"  {i}. {b['judul']} ({b['sumber']})")
                else:
                    print("⚠️ Tidak ada berita terkini.")

                pertanyaan = input("\nAda pertanyaan? (atau tekan Enter untuk analisis umum): ")
                if not pertanyaan:
                    pertanyaan = f"Berikan analisis lengkap untuk saham {saham}"
                
                print(f"⏳ Menghitung indikator teknikal {saham}...")
                indikator = get_stock_indicators(saham)
                if indikator:
                    print(f"✅ Indikator berhasil dihitung!")
                    print(f"   📈 RSI: {indikator['rsi']} → {indikator['rsi_status']}")
                    print(f"   📉 MACD: {indikator['macd_status']}")
                else:
                    print("⚠️ Indikator tidak tersedia.")

                print("\n🤖 Groq AI sedang menganalisis...\n")
                hasil = analisis_ai(pertanyaan, data_harga, berita, indikator)
                print("-" * 55)
                print(hasil)
                print("-" * 55)
                simpan_ke_excel("Saham", saham, data_harga, "", hasil)
            except Exception as e:
                if "403" in str(e) or "PermissionDenied" in str(type(e).__name__):
                    print(f"❌ Groq API error - coba lagi atau gunakan VPN!")
                else:
                    print(f"❌ Kode saham tidak ditemukan! Pastikan format benar.")
                    print(f"Detail: {e}")
                
        elif pilihan == "3":
            print("\nPilih jenis alert:")
            print("1. Crypto")
            print("2. Saham")
            jenis_alert = input("Pilihan (1/2): ")
            
            if jenis_alert == "1":
                nama = input("Nama crypto (contoh: bitcoin): ").lower()
                jenis = "crypto"
            else:
                nama = input("Kode saham (contoh: BBCA.JK): ").upper()
                jenis = "saham"
            
            kondisi = input("Alert ketika harga (naik/turun): ").lower()
            harga_target = float(input("Harga target (USD untuk crypto, IDR untuk saham): "))
            tambah_alert(jenis, nama, harga_target, kondisi)
            
            # Jalankan monitor di background
            if len(alert_list) == 1:
                t = threading.Thread(target=jalankan_monitor, daemon=True)
                t.start()
                print("🔄 Monitor harga berjalan di background!")

        elif pilihan == "4":
            if not alert_list:
                print("\n⚠️ Tidak ada alert aktif!")
            else:
                print("\n📋 Alert Aktif:")
                for i, a in enumerate(alert_list, 1):
                    print(f"  {i}. {a['nama_aset']} → {a['kondisi']} {a['harga_target']}")

        elif pilihan == "5":
            if not alert_list:
                print("\n⚠️ Tidak ada alert yang bisa dihapus!")
            else:
                print("\n📋 Pilih alert yang ingin dihapus:")
                for i, a in enumerate(alert_list, 1):
                    print(f"  {i}. {a['nama_aset']} → {a['kondisi']} {a['harga_target']}")
                try:
                    nomor = int(input("Masukkan nomor alert: ")) - 1
                    dihapus = alert_list.pop(nomor)
                    simpan_alert()
                    print(f"✅ Alert {dihapus['nama_aset']} berhasil dihapus!")
                except:
                    print("❌ Nomor tidak valid!")

        elif pilihan == "6":
            print("\nSampai jumpa! 👋")
            break
        else:
            print("❌ Pilihan tidak valid!")

if __name__ == "__main__":
    main()