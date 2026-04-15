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
import gspread
from google.oauth2.service_account import Credentials
import json
import re

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
# DEFAULT WEIGHTS & CONFIG
# ==============================
DEFAULT_WEIGHTS = {
    "rsi": 1.0,
    "macd": 1.0,
    "trend": 1.0,
    "volume": 1.0,
    "sentimen": 1.0
}
DEFAULT_MODAL = 1_000_000  # Rp 1.000.000

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
# HELPER: MARKET CONDITION
# ==============================
def detect_market_condition(df, ma50, ma200):
    """
    Tentukan kondisi market: TRENDING, SIDEWAYS, atau VOLATILE
    Berdasarkan volatilitas returns dan jarak MA50-MA200
    """
    if len(df) < 20:
        return "UNKNOWN"
    
    close = df["close"]
    
    # Hitung volatilitas dari daily returns (std dev 20 hari terakhir)
    returns = close.pct_change().dropna()
    if len(returns) < 20:
        volatility = returns.std() * 100
    else:
        volatility = returns.iloc[-20:].std() * 100
    
    # Volatilitas tinggi → VOLATILE
    if volatility > 3.0:
        return "VOLATILE"
    
    # Cek dari MA50 vs MA200
    if ma50 is not None and ma200 is not None:
        current_price = close.iloc[-1]
        if current_price > 0:
            ma_diff_pct = abs(ma50 - ma200) / current_price * 100
            if ma_diff_pct < 2:
                return "SIDEWAYS"
            else:
                return "TRENDING"
    
    # Fallback: gunakan price range 20 hari
    recent = close.iloc[-20:]
    current_price = close.iloc[-1]
    if current_price > 0:
        price_range_pct = (recent.max() - recent.min()) / current_price * 100
        if price_range_pct < 5:
            return "SIDEWAYS"
        elif price_range_pct > 20:
            return "VOLATILE"
    
    return "TRENDING"

# ==============================
# INDIKATOR TEKNIKAL CRYPTO (ENHANCED)
# ==============================
def get_crypto_indicators(nama_crypto):
    try:
        url = f"https://api.coingecko.com/api/v3/coins/{nama_crypto}/market_chart"
        # Ambil 300 hari untuk MA200
        params = {"vs_currency": "usd", "days": "300", "interval": "daily"}
        response = requests.get(url, params=params)
        data = response.json()
        
        prices = [x[1] for x in data.get("prices", [])]
        volumes = [x[1] for x in data.get("total_volumes", [])]
        
        if not prices:
            return None
        
        df = pd.DataFrame({
            "close": prices,
            "volume": volumes[:len(prices)] if volumes else [0] * len(prices)
        })
        
        # RSI (14)
        df["rsi"] = ta.momentum.RSIIndicator(df["close"], window=14).rsi()
        
        # MACD
        macd_ind = ta.trend.MACD(df["close"])
        df["macd"] = macd_ind.macd()
        df["macd_signal"] = macd_ind.macd_signal()
        
        # MA50 & MA200
        df["ma50"] = df["close"].rolling(window=50).mean()
        df["ma200"] = df["close"].rolling(window=200).mean()
        
        # Volume moving average (20 hari)
        df["vol_avg"] = df["volume"].rolling(window=20).mean()
        
        # Ambil nilai terakhir
        rsi = round(df["rsi"].iloc[-1], 2) if pd.notna(df["rsi"].iloc[-1]) else 50.0
        macd_val = round(df["macd"].iloc[-1], 4) if pd.notna(df["macd"].iloc[-1]) else 0
        macd_sig = round(df["macd_signal"].iloc[-1], 4) if pd.notna(df["macd_signal"].iloc[-1]) else 0
        ma50 = round(df["ma50"].iloc[-1], 4) if pd.notna(df["ma50"].iloc[-1]) else None
        ma200 = round(df["ma200"].iloc[-1], 4) if pd.notna(df["ma200"].iloc[-1]) else None
        
        current_vol = df["volume"].iloc[-1] if pd.notna(df["volume"].iloc[-1]) else 0
        avg_vol = df["vol_avg"].iloc[-1] if pd.notna(df["vol_avg"].iloc[-1]) else current_vol
        
        # Support & Resistance (dari 20 hari terakhir)
        recent_closes = df["close"].iloc[-20:]
        support = round(recent_closes.min(), 4)
        resistance = round(recent_closes.max(), 4)
        current_price = round(df["close"].iloc[-1], 4)
        
        # === INTERPRETASI ===
        
        # RSI
        if rsi < 30:
            rsi_status = "OVERSOLD"
        elif rsi > 70:
            rsi_status = "OVERBOUGHT"
        else:
            rsi_status = "NORMAL"
        
        # MACD
        macd_status = "BULLISH" if macd_val > macd_sig else "BEARISH"
        
        # Trend (MA50 vs MA200)
        trend_status = "NEUTRAL"
        if ma50 is not None and ma200 is not None:
            if ma50 > ma200:
                trend_status = "BULLISH"
            else:
                trend_status = "BEARISH"
        
        # Volume
        vol_ratio = round(current_vol / avg_vol, 2) if avg_vol > 0 else 1.0
        if vol_ratio > 1.2:
            volume_status = "TINGGI"
        elif vol_ratio < 0.8:
            volume_status = "RENDAH"
        else:
            volume_status = "NORMAL"
        
        # Market condition
        market_condition = detect_market_condition(df, ma50, ma200)
        
        return {
            "rsi": rsi,
            "rsi_status": rsi_status,
            "macd": macd_val,
            "macd_signal": macd_sig,
            "macd_status": macd_status,
            "ma50": ma50,
            "ma200": ma200,
            "trend_status": trend_status,
            "volume_current": round(current_vol, 2),
            "volume_avg": round(avg_vol, 2),
            "volume_ratio": vol_ratio,
            "volume_status": volume_status,
            "support": support,
            "resistance": resistance,
            "current_price": current_price,
            "market_condition": market_condition
        }
    except Exception as e:
        print(f"⚠️ Error crypto indicators: {e}")
        return None

# ==============================
# INDIKATOR TEKNIKAL SAHAM (ENHANCED)
# ==============================
def get_stock_indicators(kode_saham):
    try:
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{kode_saham}"
        # Ambil 1 tahun data untuk MA200
        params = {"interval": "1d", "range": "1y"}
        headers = {"User-Agent": "Mozilla/5.0"}
        response = requests.get(url, params=params, headers=headers)
        data = response.json()
        
        result = data["chart"]["result"][0]
        quotes = result["indicators"]["quote"][0]
        
        closes = quotes["close"]
        volumes = quotes.get("volume", [])
        highs = quotes.get("high", [])
        lows = quotes.get("low", [])
        
        # Filter None values — simpan index valid
        valid_data = []
        for i in range(len(closes)):
            if closes[i] is not None:
                valid_data.append({
                    "close": closes[i],
                    "volume": volumes[i] if i < len(volumes) and volumes[i] is not None else 0,
                    "high": highs[i] if i < len(highs) and highs[i] is not None else closes[i],
                    "low": lows[i] if i < len(lows) and lows[i] is not None else closes[i]
                })
        
        if not valid_data:
            return None
        
        df = pd.DataFrame(valid_data)
        
        # RSI (14)
        df["rsi"] = ta.momentum.RSIIndicator(df["close"], window=14).rsi()
        
        # MACD
        macd_ind = ta.trend.MACD(df["close"])
        df["macd"] = macd_ind.macd()
        df["macd_signal"] = macd_ind.macd_signal()
        
        # MA50 & MA200
        df["ma50"] = df["close"].rolling(window=50).mean()
        df["ma200"] = df["close"].rolling(window=200).mean()
        
        # Volume moving average (20 hari)
        df["vol_avg"] = df["volume"].rolling(window=20).mean()
        
        # Ambil nilai terakhir
        rsi = round(df["rsi"].iloc[-1], 2) if pd.notna(df["rsi"].iloc[-1]) else 50.0
        macd_val = round(df["macd"].iloc[-1], 4) if pd.notna(df["macd"].iloc[-1]) else 0
        macd_sig = round(df["macd_signal"].iloc[-1], 4) if pd.notna(df["macd_signal"].iloc[-1]) else 0
        ma50 = round(df["ma50"].iloc[-1], 4) if pd.notna(df["ma50"].iloc[-1]) else None
        ma200 = round(df["ma200"].iloc[-1], 4) if pd.notna(df["ma200"].iloc[-1]) else None
        
        current_vol = df["volume"].iloc[-1] if pd.notna(df["volume"].iloc[-1]) else 0
        avg_vol = df["vol_avg"].iloc[-1] if pd.notna(df["vol_avg"].iloc[-1]) else current_vol
        
        # Support & Resistance (dari high/low 20 hari terakhir)
        recent_high = df["high"].iloc[-20:]
        recent_low = df["low"].iloc[-20:]
        support = round(recent_low.min(), 4)
        resistance = round(recent_high.max(), 4)
        current_price = round(df["close"].iloc[-1], 4)
        
        # === INTERPRETASI ===
        
        # RSI
        if rsi < 30:
            rsi_status = "OVERSOLD"
        elif rsi > 70:
            rsi_status = "OVERBOUGHT"
        else:
            rsi_status = "NORMAL"
        
        # MACD
        macd_status = "BULLISH" if macd_val > macd_sig else "BEARISH"
        
        # Trend
        trend_status = "NEUTRAL"
        if ma50 is not None and ma200 is not None:
            if ma50 > ma200:
                trend_status = "BULLISH"
            else:
                trend_status = "BEARISH"
        
        # Volume
        vol_ratio = round(current_vol / avg_vol, 2) if avg_vol > 0 else 1.0
        if vol_ratio > 1.2:
            volume_status = "TINGGI"
        elif vol_ratio < 0.8:
            volume_status = "RENDAH"
        else:
            volume_status = "NORMAL"
        
        # Market condition
        market_condition = detect_market_condition(df, ma50, ma200)
        
        return {
            "rsi": rsi,
            "rsi_status": rsi_status,
            "macd": macd_val,
            "macd_signal": macd_sig,
            "macd_status": macd_status,
            "ma50": ma50,
            "ma200": ma200,
            "trend_status": trend_status,
            "volume_current": round(current_vol, 2),
            "volume_avg": round(avg_vol, 2),
            "volume_ratio": vol_ratio,
            "volume_status": volume_status,
            "support": support,
            "resistance": resistance,
            "current_price": current_price,
            "market_condition": market_condition
        }
    except Exception as e:
        print(f"⚠️ Error stock indicators: {e}")
        return None

# ==============================
# GOOGLE SHEETS CLIENT
# ==============================
def get_sheets_client():
    try:
        creds_json = os.getenv("GOOGLE_CREDENTIALS")
        if creds_json:
            creds_dict = json.loads(creds_json)
        else:
            with open("credentials.json", "r") as f:
                creds_dict = json.load(f)
                
        scopes = [
            "https://spreadsheets.google.com/feeds",
            "https://www.googleapis.com/auth/drive"
        ]
        creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
        gc = gspread.authorize(creds)
        return gc
    except Exception as e:
        print(f"❌ Google Sheets error: {e}")
        return None

# ==============================
# 1. ADAPTIVE LEARNING
# ==============================
def get_trade_history():
    """Ambil histori trade dari sheet Performance untuk adaptive learning"""
    try:
        gc = get_sheets_client()
        if not gc:
            return []
        
        sheet_id = os.getenv("GOOGLE_SHEETS_ID")
        spreadsheet = gc.open_by_key(sheet_id)
        ws = spreadsheet.worksheet("Performance")
        
        all_values = ws.get_all_values()
        if len(all_values) < 2:
            return []
        
        # Cari header row
        header_idx = 0
        for i, row in enumerate(all_values):
            if "Tanggal" in row or "Status" in row:
                header_idx = i
                break
        
        headers = all_values[header_idx]
        data_rows = all_values[header_idx + 1:]
        
        trades = []
        for row in data_rows:
            if len(row) >= len(headers):
                trade = dict(zip(headers, row))
            elif len(row) > 0 and row[0]:
                padded = row + [""] * (len(headers) - len(row))
                trade = dict(zip(headers, padded))
            else:
                continue
            
            # Parse skor_detail jika ada
            skor_json = trade.get("Skor Detail", "")
            if skor_json:
                try:
                    trade["skor_detail"] = json.loads(skor_json)
                except:
                    trade["skor_detail"] = None
            else:
                trade["skor_detail"] = None
            
            # Normalize
            trade["hasil"] = trade.get("Hasil", "")
            trade["status"] = trade.get("Status", "")
            
            if trade.get("status") == "CLOSED":
                trades.append(trade)
        
        return trades
    except Exception as e:
        print(f"⚠️ Error ambil trade history: {e}")
        return []

def calculate_adaptive_weights(trade_history):
    """
    Jika histori >= 30 trade CLOSED dengan skor_detail:
    - Evaluasi win rate tiap indikator
    - Naikkan bobot indikator dengan win rate tinggi
    - Turunkan bobot indikator dengan win rate rendah
    """
    weights = DEFAULT_WEIGHTS.copy()
    
    # Filter trades yang punya skor_detail
    trades_with_scores = [t for t in trade_history if t.get("skor_detail")]
    
    if len(trades_with_scores) < 30:
        return weights
    
    for indicator in ["rsi", "macd", "trend", "volume", "sentimen"]:
        wins = 0
        total = 0
        
        for trade in trades_with_scores:
            scores = trade["skor_detail"]
            if indicator in scores and scores[indicator] != 0:
                total += 1
                if trade.get("hasil") == "WIN":
                    wins += 1
        
        if total >= 10:
            win_rate = wins / total
            if win_rate > 0.65:
                weights[indicator] = 1.5  # Naikkan bobot (+50%)
            elif win_rate > 0.55:
                weights[indicator] = 1.2  # Sedikit naik
            elif win_rate < 0.35:
                weights[indicator] = 0.5  # Turunkan bobot (-50%)
            elif win_rate < 0.45:
                weights[indicator] = 0.8  # Sedikit turun
    
    return weights

# ==============================
# 4. ANALISIS BERITA (IMPROVED)
# ==============================
def analyze_news(berita, symbol):
    """
    Analisis berita dengan label: LANGSUNG / SEKTOR / MAKRO
    Ambil maksimal 3 berita, tentukan sentimen, skor, dan dampak
    """
    if not berita:
        return {
            "berita_label": [],
            "status": "NETRAL",
            "skor": 0.0,
            "dampak": "Tidak ada berita signifikan"
        }
    
    # Ambil maksimal 3 berita
    top_berita = berita[:3]
    headlines = "\n".join([f"- {b['judul']} ({b.get('sumber', 'N/A')})" for b in top_berita])
    
    # Deteksi label berita (LANGSUNG/SEKTOR/MAKRO)
    symbol_upper = symbol.upper()
    is_crypto = not symbol.endswith(".JK")
    
    labeled_berita = []
    for b in top_berita:
        judul = b.get('judul', '').lower()
        label = "LANGSUNG"
        if is_crypto:
            if any(x in judul for x in ['sector', 'industry', 'mining', 'energy', 'bank', 'tech']):
                label = "SEKTOR"
            if any(x in judul for x in ['fed', 'interest rate', 'inflation', 'gdp', 'economy', 'recession', 'employment']):
                label = "MAKRO"
        else:
            if symbol_upper in judul:
                label = "LANGSUNG"
            elif any(x in judul for x in ['sector', 'industry', 'banking', 'tech']):
                label = "SEKTOR"
            else:
                label = "MAKRO"
        labeled_berita.append({
            "judul": b.get('judul', ''),
            "sumber": b.get('sumber', 'N/A'),
            "label": label
        })
    
    prompt = f"""Analisis sentimen berita untuk aset {symbol}.

Berita:
{headlines}

JAWAB HANYA dalam format JSON (tanpa markdown, tanpa penjelasan tambahan):
{{"status": "POSITIF/NETRAL/NEGATIF", "skor": <float -1.0 sampai 1.0>, "dampak": "<dampak ke harga dalam 1 kalimat>"}}"""
    
    try:
        response = client.chat.completions.create(
            model="meta-llama/llama-3.3-70b-instruct",
            max_tokens=200,
            messages=[{"role": "user", "content": prompt}]
        )
        result = response.choices[0].message.content.strip()
        
        if "```" in result:
            parts = result.split("```")
            for part in parts:
                part = part.strip()
                if part.startswith("json"):
                    part = part[4:].strip()
                if part.startswith("{"):
                    result = part
                    break
        
        json_match = re.search(r'\{[^}]+\}', result)
        if json_match:
            parsed = json.loads(json_match.group())
            status = parsed.get("status", "NETRAL").upper()
            if status not in ["POSITIF", "NETRAL", "NEGATIF"]:
                status = "NETRAL"
            skor = max(-1.0, min(1.0, float(parsed.get("skor", 0))))
            dampak = str(parsed.get("dampak", "Tidak ada dampak signifikan"))
            
            return {
                "berita_label": labeled_berita,
                "status": status,
                "skor": skor,
                "dampak": dampak
            }
        
        return {
            "berita_label": labeled_berita,
            "status": "NETRAL",
            "skor": 0.0,
            "dampak": "Gagal parsing sentimen"
        }
    except Exception as e:
        print(f"⚠️ Error sentiment analysis: {e}")
        return {
            "berita_label": labeled_berita,
            "status": "NETRAL",
            "skor": 0.0,
            "dampak": "Gagal menganalisis sentimen"
        }

# ==============================
# 5. SCORING ENGINE
# ==============================
def calculate_score(indikator, sentimen, weights, market_condition):
    """
    Hitung skor deterministik dari semua indikator.
    
    RSI: +2 / 0 / -2
    MACD: +2 / -2
    Trend: +3 / 0 / -3
    Volume: +1 / -1
    Sentimen: +2 / 0 / -2
    
    Total skor = jumlah semua × bobot adaptif
    """
    scores = {}
    
    # RSI Score
    rsi_status = indikator.get("rsi_status", "NORMAL")
    if rsi_status == "OVERSOLD":
        scores["rsi"] = 2
    elif rsi_status == "OVERBOUGHT":
        scores["rsi"] = -2
    else:
        scores["rsi"] = 0
    
    # MACD Score
    macd_status = indikator.get("macd_status", "BEARISH")
    scores["macd"] = 2 if macd_status == "BULLISH" else -2
    
    # Trend Score (MA50 vs MA200)
    trend_status = indikator.get("trend_status", "NEUTRAL")
    if trend_status == "BULLISH":
        scores["trend"] = 3
    elif trend_status == "BEARISH":
        scores["trend"] = -3
    else:
        scores["trend"] = 0
    
    # Volume Score — konfirmasi arah
    volume_status = indikator.get("volume_status", "NORMAL")
    direction = scores["macd"] + scores["trend"]
    
    if volume_status == "TINGGI":
        if direction > 0:
            scores["volume"] = 1   # Konfirmasi bullish
        elif direction < 0:
            scores["volume"] = -1  # Konfirmasi bearish
        else:
            scores["volume"] = 0   # Mixed direction
    elif volume_status == "RENDAH":
        scores["volume"] = -1  # Volume lemah = sinyal lemah
    else:
        scores["volume"] = 0
    
    # Sentimen Score
    sentimen_skor = sentimen.get("skor", 0)
    if sentimen_skor > 0.3:
        scores["sentimen"] = 2
    elif sentimen_skor < -0.3:
        scores["sentimen"] = -2
    else:
        scores["sentimen"] = 0
    
    # === MARKET CONDITION ADJUSTMENT ===
    # Trending → fokus MA & MACD (boost trend/macd, kurangi RSI)
    # Sideways → fokus RSI & S/R (boost RSI, kurangi trend)
    # Volatile → tidak ubah scoring, handle di SL/position sizing
    if market_condition == "TRENDING":
        scores["trend"] = round(scores["trend"] * 1.3)
        scores["macd"] = round(scores["macd"] * 1.3)
        scores["rsi"] = round(scores["rsi"] * 0.6)
    elif market_condition == "SIDEWAYS":
        scores["rsi"] = round(scores["rsi"] * 1.3)
        scores["trend"] = round(scores["trend"] * 0.5)
    
    # === APPLY ADAPTIVE WEIGHTS ===
    total = 0.0
    for key in scores:
        w = weights.get(key, 1.0)
        total += scores[key] * w
    
    return scores, round(total, 1)

# ==============================
# 8. NO TRADE ZONE
# ==============================
def detect_no_trade_zone(indikator, skor_detail):
    """
    Jika sideways + volume lemah + konflik indikator → Hindari entry
    """
    market = indikator.get("market_condition", "")
    vol_status = indikator.get("volume_status", "")
    
    # Cek konflik indikator (ada yang positif dan negatif)
    positive_count = sum(1 for v in skor_detail.values() if v > 0)
    negative_count = sum(1 for v in skor_detail.values() if v < 0)
    has_conflict = positive_count > 0 and negative_count > 0
    
    if market == "SIDEWAYS" and vol_status == "RENDAH" and has_conflict:
        return True
    
    return False

# ==============================
# 9. ENTRY / SL / TP CALCULATION
# ==============================
def calculate_entry_sl_tp(harga, sinyal, indikator):
    """
    Hitung Entry, Stop Loss, dan Take Profit
    SL: 2-5% | TP: Risk:Reward >= 1:2
    """
    support = indikator.get("support", harga * 0.97)
    resistance = indikator.get("resistance", harga * 1.03)
    market_condition = indikator.get("market_condition", "TRENDING")
    
    # SL percentage: volatile → lebih besar
    sl_pct = 0.05 if market_condition == "VOLATILE" else 0.03
    
    if sinyal == "BELI":
        entry = harga
        # SL di bawah support atau persentase, ambil yang lebih dekat tapi min 2%
        sl = min(entry * (1 - sl_pct), support * 0.99)
        sl = min(sl, entry * (1 - 0.02))  # Minimal 2% di bawah entry
        risk = entry - sl
        tp = entry + (risk * 2)  # Minimum 1:2 RR
        tp = max(tp, resistance)  # Setidaknya sampai resistance
    elif sinyal == "JUAL":
        entry = harga
        sl = max(entry * (1 + sl_pct), resistance * 1.01)
        sl = max(sl, entry * (1 + 0.02))
        risk = sl - entry
        tp = entry - (risk * 2)
        tp = min(tp, support)
    else:  # HOLD
        entry = harga
        sl = harga * 0.97
        tp = harga * 1.03
    
    return round(entry, 6), round(sl, 6), round(tp, 6)

# ==============================
# 10. COPY TRADING — POSITION SIZING
# ==============================
def calculate_position_size(modal, entry, sl, sinyal, market_condition="TRENDING"):
    """
    Position Size = (Risk% × Modal) / |Entry - Stop Loss|
    Risk: 1% normal, 0.5% volatile
    """
    if sinyal == "HOLD" or entry == 0:
        return 0
    
    # Risk per trade: 1% normal, 0.5% kalau volatile
    risk_pct = 0.005 if market_condition == "VOLATILE" else 0.01
    risk_per_trade = modal * risk_pct
    
    risk_per_unit = abs(entry - sl)
    
    if risk_per_unit == 0:
        return 0
    
    size = risk_per_trade / risk_per_unit
    return round(size, 6)

# ==============================
# AI REASONING (LLM untuk alasan saja)
# ==============================
def get_ai_reasoning(symbol, indikator, sentimen, skor_detail, total_skor, sinyal, market_condition):
    """
    Minta AI menjelaskan ALASAN di balik sinyal.
    Scoring sudah ditentukan secara deterministik — AI hanya memberi narasi.
    """
    prompt = f"""Kamu adalah AI Trading Analyst profesional. Berikan ALASAN SINGKAT (3-5 kalimat) dalam Bahasa Indonesia mengapa sinyal {sinyal} diberikan untuk {symbol}.

Data Analisis:
- Kondisi Market: {market_condition}
- RSI: {indikator.get('rsi', 'N/A')} ({indikator.get('rsi_status', 'N/A')}) → skor: {skor_detail.get('rsi', 0)}
- MACD: {indikator.get('macd_status', 'N/A')} → skor: {skor_detail.get('macd', 0)}
- Trend: {indikator.get('trend_status', 'N/A')} (MA50: {indikator.get('ma50', 'N/A')} | MA200: {indikator.get('ma200', 'N/A')}) → skor: {skor_detail.get('trend', 0)}
- Volume: {indikator.get('volume_status', 'N/A')} (rasio: {indikator.get('volume_ratio', 'N/A')}x) → skor: {skor_detail.get('volume', 0)}
- Sentimen: {sentimen.get('status', 'N/A')} (skor: {sentimen.get('skor', 0)}) → skor: {skor_detail.get('sentimen', 0)}
- Total Skor: {total_skor}
- S/R: Support {indikator.get('support', 'N/A')} | Resistance {indikator.get('resistance', 'N/A')}

Jelaskan singkat dan jelas:
1. Mengapa sinyal ini diberikan
2. Faktor utama yang mendukung
3. Risiko yang perlu diwaspadai

Jawab langsung dalam 3-5 kalimat tanpa header."""
    
    try:
        response = client.chat.completions.create(
            model="meta-llama/llama-3.3-70b-instruct",
            max_tokens=500,
            messages=[{"role": "user", "content": prompt}]
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        return f"Sinyal {sinyal} diberikan berdasarkan total skor {total_skor}. Analisis menunjukkan kondisi market {market_condition} dengan kombinasi indikator teknikal dan sentimen pasar."

# ==============================
# FORMAT OUTPUT
# ==============================
def fmt_price(price, currency="USD"):
    """Format harga sesuai currency"""
    if price is None:
        return "N/A"
    if currency == "IDR":
        return f"Rp {price:,.0f}"
    elif price >= 1:
        return f"${price:,.2f}"
    else:
        return f"${price:,.6f}"

def format_analysis_output(symbol, harga, harga_idr, indikator, sentimen,
                           sinyal, total_skor, confidence, entry, sl, tp,
                           risk_level, rr_ratio, modal, position_size, alasan,
                           market_condition, skor_detail, weights, jenis, no_trade):
    """Format output sesuai template 10-point system"""
    
    # Currency tergantung jenis aset
    if jenis == "Crypto":
        curr = "USD"
        harga_display = fmt_price(harga, "USD")
        if harga_idr:
            harga_display += f" (Rp {harga_idr:,.0f})"
        entry_display = fmt_price(entry, "USD")
        sl_display = fmt_price(sl, "USD")
        tp_display = fmt_price(tp, "USD")
    else:
        # Saham Indonesia pakai IDR, US pakai USD
        if symbol.endswith(".JK"):
            curr = "IDR"
        else:
            curr = "USD"
        harga_display = fmt_price(harga, curr)
        entry_display = fmt_price(entry, curr)
        sl_display = fmt_price(sl, curr)
        tp_display = fmt_price(tp, curr)
    
    # Support/Resistance display
    s_display = fmt_price(indikator.get("support"), curr)
    r_display = fmt_price(indikator.get("resistance"), curr)
    
    # MA display
    ma50_str = fmt_price(indikator.get("ma50"), curr) if indikator.get("ma50") else "N/A"
    ma200_str = fmt_price(indikator.get("ma200"), curr) if indikator.get("ma200") else "N/A"
    
    # Adaptive weights info
    weights_modified = any(w != 1.0 for w in weights.values())
    weights_note = ""
    if weights_modified:
        mods = []
        for k, v in weights.items():
            if v != 1.0:
                mods.append(f"{k.upper()}: {v}x")
        weights_note = f"\n📐 Bobot Adaptif: {', '.join(mods)}"
    
    # No-trade warning
    no_trade_warning = ""
    if no_trade:
        no_trade_warning = "\n⛔ NO TRADE ZONE: Sideways + Volume lemah + Konflik indikator → Hindari entry!"
    
    # Format berita dengan label
    berita_list = sentimen.get("berita_label", [])
    if berita_list:
        berita_str = "\n".join([f"  • [{b['label']}] {b['judul'][:60]}..." for b in berita_list[:3]])
    else:
        berita_str = "Tidak ada berita signifikan"
    
    output = f"""📊 ANALISIS {symbol.upper()}
💰 Harga: {harga_display}
🏪 Market: {market_condition}

📈 Teknikal:
• RSI: {indikator.get('rsi', 'N/A')} → {indikator.get('rsi_status', 'N/A')} (skor: {skor_detail.get('rsi', 0)})
• MACD: {indikator.get('macd_status', 'N/A')} (skor: {skor_detail.get('macd', 0)})
• Trend: {indikator.get('trend_status', 'N/A')} | MA50: {ma50_str} | MA200: {ma200_str} (skor: {skor_detail.get('trend', 0)})
• Volume: {indikator.get('volume_status', 'N/A')} (rasio: {indikator.get('volume_ratio', 'N/A')}x) (skor: {skor_detail.get('volume', 0)})
• S/R: Support {s_display} | Resistance {r_display}

📰 Sentimen:
{berita_str}
• Status: {sentimen.get('status', 'N/A')}
• Skor: {sentimen.get('skor', 0)}
• Dampak: {sentimen.get('dampak', 'N/A')}

🎯 Sinyal: {sinyal}
📊 Skor: {'+' if total_skor > 0 else ''}{total_skor}
🔥 Confidence: {confidence:.0f}%{no_trade_warning}{weights_note}

📌 Rekomendasi:
• Entry: {entry_display}
• SL: {sl_display}
• TP: {tp_display}
• Risk: {risk_level}
• RR: {rr_ratio}

💼 Copy Trade:
• Modal: Rp {modal:,.0f}
• Size: {position_size:,.6f}
• Status: {'OPEN' if sinyal != 'HOLD' else '-'}
• P/L: -

🧠 Alasan:
{alasan}

⚠️ Disclaimer: Bukan nasihat keuangan. Selalu lakukan riset sendiri dan kelola risiko dengan bijak."""
    
    return output

# ==============================
# ANALISIS AI V2 — MAIN ORCHESTRATOR
# ==============================
def analisis_ai_v2(symbol, jenis, data_harga, berita, indikator, modal=DEFAULT_MODAL):
    """
    Fungsi analisis utama — 10-Point System
    
    Returns: (formatted_output_string, analysis_data_dict)
    """
    if not indikator:
        empty_data = {
            "sinyal": "HOLD", "entry": 0, "sl": 0, "tp": 0,
            "skor": 0, "confidence": 0, "risk_level": "HIGH",
            "skor_detail": {}, "position_size": 0
        }
        return "⚠️ Data indikator tidak tersedia. Coba lagi nanti.", empty_data
    
    # 1. Ambil harga saat ini
    if jenis == "Crypto":
        aset_key = list(data_harga.keys())[0]
        harga = data_harga[aset_key].get("usd", 0)
        harga_idr = data_harga[aset_key].get("idr", 0)
    else:
        harga = data_harga.get("harga", 0)
        harga_idr = None
    
    # 2. Adaptive Learning — ambil bobot dari histori
    trade_history = get_trade_history()
    weights = calculate_adaptive_weights(trade_history)
    
    # 3. Market condition (sudah dihitung di indikator)
    market_condition = indikator.get("market_condition", "UNKNOWN")
    
    # 4. Analisis Berita
    sentimen = analyze_news(berita, symbol)
    
    # 5. Calculate Scores (deterministik)
    skor_detail, total_skor = calculate_score(indikator, sentimen, weights, market_condition)
    
    # 6. Determine Signal
    if total_skor >= 5:
        sinyal = "BELI"
    elif total_skor <= -5:
        sinyal = "JUAL"
    else:
        sinyal = "HOLD"
    
    # 7. Confidence
    confidence = min(abs(total_skor) / 10 * 100, 100)
    if confidence < 60:
        sinyal = "HOLD"
    
    # 8. No-Trade Zone Check
    no_trade = detect_no_trade_zone(indikator, skor_detail)
    if no_trade:
        sinyal = "HOLD"
    
    # 9. Entry, SL, TP
    entry, sl, tp = calculate_entry_sl_tp(harga, sinyal, indikator)
    
    # 10. Risk & Reward
    if sinyal == "BELI" and entry > 0:
        risk_pct = abs(entry - sl) / entry * 100
        reward_pct = abs(tp - entry) / entry * 100
    elif sinyal == "JUAL" and entry > 0:
        risk_pct = abs(sl - entry) / entry * 100
        reward_pct = abs(entry - tp) / entry * 100
    else:
        risk_pct = 0
        reward_pct = 0
    
    rr_ratio = f"1:{reward_pct / risk_pct:.1f}" if risk_pct > 0 else "N/A"
    
    # Risk Level
    if confidence < 70:
        risk_level = "HIGH"
    elif confidence < 85:
        risk_level = "MEDIUM"
    else:
        risk_level = "LOW"
    
    # Position Sizing
    position_size = calculate_position_size(modal, entry, sl, sinyal, market_condition)
    
    # AI Reasoning (LLM call — hanya untuk penjelasan)
    alasan = get_ai_reasoning(symbol, indikator, sentimen, skor_detail, total_skor, sinyal, market_condition)
    
    # Format Output
    output = format_analysis_output(
        symbol=symbol,
        harga=harga,
        harga_idr=harga_idr,
        indikator=indikator,
        sentimen=sentimen,
        sinyal=sinyal,
        total_skor=total_skor,
        confidence=confidence,
        entry=entry,
        sl=sl,
        tp=tp,
        risk_level=risk_level,
        rr_ratio=rr_ratio,
        modal=modal,
        position_size=position_size,
        alasan=alasan,
        market_condition=market_condition,
        skor_detail=skor_detail,
        weights=weights,
        jenis=jenis,
        no_trade=no_trade
    )
    
    analysis_data = {
        "sinyal": sinyal,
        "entry": entry,
        "sl": sl,
        "tp": tp,
        "skor": total_skor,
        "confidence": confidence,
        "risk_level": risk_level,
        "skor_detail": skor_detail,
        "position_size": position_size,
        "market_condition": market_condition,
        "no_trade": no_trade
    }
    
    return output, analysis_data

# ==============================
# LEGACY ANALYSIS (backward compat)
# ==============================
def analisis_ai(pertanyaan, data_harga, berita, indikator):
    """Legacy function — tetap ada untuk backward compatibility"""
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
    6. Berikan rekomendasi trading:
       - Entry Price: harga ideal untuk masuk posisi
       - Stop Loss: batas harga keluar jika salah (sekitar 3-5% dari entry)
       - Take Profit: target harga ambil untung (sekitar 5-10% dari entry)
       - Risk Level: LOW / MEDIUM / HIGH
       - Risk/Reward Ratio: perbandingan risiko vs potensi untung
    7. Jelaskan alasannya secara singkat
    8. Ingatkan bahwa investasi selalu ada risikonya
    
    Jawab dalam Bahasa Indonesia.
    """
    
    response = client.chat.completions.create(
        model="meta-llama/llama-3.3-70b-instruct",
        max_tokens=1500,
        messages=[{"role": "user", "content": prompt}]
    )
    return response.choices[0].message.content

def parse_trading_info(hasil_analisis, harga_sekarang):
    """Ekstrak Entry, SL, TP dari teks analisis AI (legacy)"""
    entry = harga_sekarang
    sl = harga_sekarang * 0.95
    tp = harga_sekarang * 1.10
    sinyal = "HOLD"
    
    # Deteksi sinyal
    if "BELI" in hasil_analisis.upper():
        sinyal = "BELI"
    elif "JUAL" in hasil_analisis.upper():
        sinyal = "JUAL"
    
    # Cari angka setelah "Entry Price"
    entry_match = re.search(r'Entry Price[:\s]+Rp?\s?([\d.,]+)', hasil_analisis)
    sl_match = re.search(r'Stop Loss[:\s]+Rp?\s?([\d.,]+)', hasil_analisis)
    tp_match = re.search(r'Take Profit[:\s]+Rp?\s?([\d.,]+)', hasil_analisis)
    
    if entry_match:
        try:
            entry = float(entry_match.group(1).replace(".", "").replace(",", ""))
        except:
            pass
    if sl_match:
        try:
            sl = float(sl_match.group(1).replace(".", "").replace(",", ""))
        except:
            pass
    if tp_match:
        try:
            tp = float(tp_match.group(1).replace(".", "").replace(",", ""))
        except:
            pass
    
    return sinyal, entry, sl, tp

# ==============================
# FUNGSI GOOGLE SHEETS — SIMPAN
# ==============================
def simpan_ke_sheets(jenis, nama_aset, harga_data, analisis, indikator):
    try:
        gc = get_sheets_client()
        if not gc:
            return

        sheet_id = os.getenv("GOOGLE_SHEETS_ID")
        spreadsheet = gc.open_by_key(sheet_id)

        # Cek sheet Histori, kalau tidak ada buat baru
        try:
            ws = spreadsheet.worksheet("Histori")
        except:
            ws = spreadsheet.add_worksheet("Histori", 1000, 10)
            ws.append_row([
                "Tanggal & Waktu", "Jenis", "Nama Aset",
                "Harga", "RSI", "MACD", "Sinyal AI", "Analisis"
            ])

        # Ambil data harga
        try:
            if jenis == "Crypto":
                aset_key = list(harga_data.keys())[0]
                harga = f"IDR {harga_data[aset_key].get('idr', '-'):,} | USD {harga_data[aset_key].get('usd', '-'):,}"
            else:
                harga = f"{harga_data.get('mata_uang', '')} {harga_data.get('harga', '-')}"
        except:
            harga = "-"

        # Ambil indikator
        rsi = indikator.get("rsi", "-") if indikator else "-"
        macd = indikator.get("macd_status", "-") if indikator else "-"

        # Tentukan sinyal dari teks analisis
        sinyal = "HOLD"
        analisis_upper = analisis.upper() if isinstance(analisis, str) else ""
        if "BELI" in analisis_upper:
            sinyal = "BELI"
        elif "JUAL" in analisis_upper:
            sinyal = "JUAL"

        # Tambah baris baru
        ws.append_row([
            datetime.now().strftime("%d/%m/%Y %H:%M"),
            jenis,
            nama_aset.upper(),
            harga,
            str(rsi),
            macd,
            sinyal,
            analisis[:500] if isinstance(analisis, str) else str(analisis)[:500]
        ])
        print(f"✅ Analisis tersimpan ke Google Sheets!")

    except Exception as e:
        print(f"⚠️ Gagal simpan ke Sheets: {e}")

# ==============================
# FUNGSI PERFORMANCE TRACKING
# ==============================
def catat_sinyal(jenis, nama_aset, harga_entry, sinyal, stop_loss, take_profit, skor_detail=None):
    try:
        gc = get_sheets_client()
        if not gc:
            return

        sheet_id = os.getenv("GOOGLE_SHEETS_ID")
        spreadsheet = gc.open_by_key(sheet_id)

        # Header termasuk Skor Detail untuk adaptive learning
        headers = [
            "Tanggal", "Jenis", "Aset", "Sinyal",
            "Harga Entry", "Stop Loss", "Take Profit",
            "Harga Penutupan", "Hasil", "Profit/Loss %",
            "Status", "Skor Detail"
        ]
        try:
            ws = spreadsheet.worksheet("Performance")
            first_row = ws.row_values(1)
            if not first_row or first_row[0] != "Tanggal":
                ws.insert_row(headers, 1)
                print("✅ Header Performance ditambahkan!")
        except:
            ws = spreadsheet.add_worksheet("Performance", 1000, 15)
            ws.append_row(headers)

        ws.append_row([
            datetime.now().strftime("%d/%m/%Y %H:%M"),
            jenis,
            nama_aset.upper(),
            sinyal,
            harga_entry,
            stop_loss,
            take_profit,
            "-",      # Harga penutupan (diisi nanti)
            "-",      # Hasil (WIN/LOSS)
            "-",      # Profit/Loss %
            "OPEN",   # Status
            json.dumps(skor_detail) if skor_detail else ""
        ])
        print(f"✅ Sinyal dicatat ke Performance Tracker!")

    except Exception as e:
        print(f"⚠️ Gagal catat sinyal: {e}")

def hitung_performa():
    try:
        gc = get_sheets_client()
        if not gc:
            return None

        sheet_id = os.getenv("GOOGLE_SHEETS_ID")
        spreadsheet = gc.open_by_key(sheet_id)
        ws = spreadsheet.worksheet("Performance")
        
        # Gunakan get_all_values agar lebih robust
        all_values = ws.get_all_values()
        
        if len(all_values) < 2:
            return None
        
        # Cari header row
        header_idx = 0
        for i, row in enumerate(all_values):
            if "Tanggal" in row or "Status" in row:
                header_idx = i
                break
        
        headers = all_values[header_idx]
        data_rows = all_values[header_idx + 1:]
        
        if not data_rows:
            return None
        
        # Convert ke dict
        data = []
        for row in data_rows:
            if len(row) >= len(headers):
                d = dict(zip(headers, row))
                data.append(d)
            elif len(row) > 0 and row[0]:  # Ada data tapi kolom kurang
                padded = row + [""] * (len(headers) - len(row))
                d = dict(zip(headers, padded))
                data.append(d)
        
        if not data:
            return None

        total = len(data)
        closed = [d for d in data if d.get("Status", "") == "CLOSED"]
        wins = [d for d in closed if d.get("Hasil", "") == "WIN"]
        losses = [d for d in closed if d.get("Hasil", "") == "LOSS"]
        open_signals = [d for d in data if d.get("Status", "") == "OPEN"]

        win_rate = (len(wins) / len(closed) * 100) if closed else 0

        # Hitung profit rata-rata
        profit_list = []
        for d in closed:
            try:
                pl = float(str(d.get("Profit/Loss %", "0")).replace("%", ""))
                profit_list.append(pl)
            except:
                pass

        avg_profit = sum(profit_list) / len(profit_list) if profit_list else 0
        max_loss = min(profit_list) if profit_list else 0

        return {
            "total_sinyal": total,
            "sinyal_open": len(open_signals),
            "sinyal_closed": len(closed),
            "wins": len(wins),
            "losses": len(losses),
            "win_rate": round(win_rate, 1),
            "avg_profit": round(avg_profit, 2),
            "max_drawdown": round(max_loss, 2)
        }

    except Exception as e:
        print(f"⚠️ Gagal hitung performa: {e}")
        return None

def update_sinyal_closed(nama_aset):
    try:
        gc = get_sheets_client()
        if not gc:
            return

        sheet_id = os.getenv("GOOGLE_SHEETS_ID")
        spreadsheet = gc.open_by_key(sheet_id)
        ws = spreadsheet.worksheet("Performance")
        data = ws.get_all_records()

        for i, row in enumerate(data, 2):
            if row["Aset"] == nama_aset.upper() and row["Status"] == "OPEN":
                try:
                    # Ambil harga terkini
                    if "." in nama_aset:
                        harga_skrg = get_stock_price(nama_aset)["harga"]
                    else:
                        data_harga = get_crypto_price(nama_aset)
                        aset_key = list(data_harga.keys())[0]
                        harga_skrg = data_harga[aset_key]["idr"]

                    entry = float(row["Harga Entry"])
                    sl = float(row["Stop Loss"])
                    tp = float(row["Take Profit"])
                    sinyal = row["Sinyal"]

                    # Tentukan WIN/LOSS
                    hasil = "-"
                    pl_pct = 0

                    if sinyal == "BELI":
                        if harga_skrg >= tp:
                            hasil = "WIN"
                            pl_pct = round((tp - entry) / entry * 100, 2)
                        elif harga_skrg <= sl:
                            hasil = "LOSS"
                            pl_pct = round((sl - entry) / entry * 100, 2)

                    elif sinyal == "JUAL":
                        if harga_skrg <= tp:
                            hasil = "WIN"
                            pl_pct = round((entry - tp) / entry * 100, 2)
                        elif harga_skrg >= sl:
                            hasil = "LOSS"
                            pl_pct = round((entry - sl) / entry * 100, 2)

                    if hasil != "-":
                        ws.update_cell(i, 8, harga_skrg)
                        ws.update_cell(i, 9, hasil)
                        ws.update_cell(i, 10, f"{pl_pct}%")
                        ws.update_cell(i, 11, "CLOSED")
                        print(f"✅ Sinyal {nama_aset} diupdate: {hasil} ({pl_pct}%)")

                except Exception as e:
                    print(f"⚠️ Error update sinyal: {e}")

    except Exception as e:
        print(f"⚠️ Gagal update sinyal: {e}")

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
    analisis_str = analisis if isinstance(analisis, str) else str(analisis)
    if "BELI" in analisis_str.upper():
        sinyal_detected = "BELI"
    elif "JUAL" in analisis_str.upper():
        sinyal_detected = "JUAL"
    
    # Tambah baris baru
    ws.append([
        datetime.now().strftime("%d/%m/%Y %H:%M"),
        jenis,
        nama_aset.upper(),
        harga,
        perubahan,
        sinyal_detected,
        analisis_str[:500]
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
    with open(ALERT_FILE, "w") as f:
        json.dump(alert_list, f)

def load_alert():
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

# ==============================
# MENU UTAMA
# ==============================
def main():
    print("=" * 60)
    print("   CRYPTO & SAHAM AGENT v2.0 — 10-Point Analysis System")
    print("   Powered by OpenRouter AI + Deterministic Scoring")
    print("=" * 60)

    load_alert()
    modal = DEFAULT_MODAL
    
    # Jalankan monitor kalau ada alert tersimpan
    if alert_list:
        t = threading.Thread(target=jalankan_monitor, daemon=True)
        t.start()
        print("🔄 Monitor harga berjalan di background!")
    
    while True:
        print("\nPilih menu:")
        print("1. 📈 Analisis Crypto (10-Point System)")
        print("2. 📉 Analisis Saham (10-Point System)")
        print("3. 🔔 Set Alert Harga")
        print("4. 📋 Lihat Alert Aktif")
        print("5. 🗑️  Hapus Alert")
        print("6. 📊 Lihat Performa")
        print("7. 💰 Set Modal")
        print("8. 🚪 Keluar")

        pilihan = input("\nMasukkan pilihan (1-8): ")

        if pilihan == "1":
            print("\nContoh: bitcoin, ethereum, solana, dogecoin")
            crypto = input("Masukkan nama crypto: ").lower()
            print(f"\n⏳ Mengambil data harga {crypto}...")
            data_harga = get_crypto_price(crypto)
            
            if not data_harga or crypto not in data_harga:
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

            print(f"\n⏳ Menghitung indikator teknikal {crypto} (enhanced)...")
            indikator = get_crypto_indicators(crypto)
            if indikator:
                print(f"✅ Indikator berhasil dihitung!")
                print(f"   📈 RSI: {indikator['rsi']} → {indikator['rsi_status']}")
                print(f"   📉 MACD: {indikator['macd_status']}")
                print(f"   📊 Trend: {indikator['trend_status']} (MA50: {indikator.get('ma50', 'N/A')} | MA200: {indikator.get('ma200', 'N/A')})")
                print(f"   📦 Volume: {indikator['volume_status']} (rasio: {indikator['volume_ratio']}x)")
                print(f"   🏪 Market: {indikator['market_condition']}")
            else:
                print("⚠️ Indikator tidak tersedia.")

            print(f"\n🤖 AI sedang menganalisis {crypto} (10-Point System)...\n")
            hasil, analysis_data = analisis_ai_v2("crypto", "Crypto", data_harga, berita, indikator, modal)
            print("-" * 60)
            print(hasil)
            print("-" * 60)
            
            # Simpan ke Excel & Sheets
            simpan_ke_excel("Crypto", crypto, data_harga, "", hasil)
            simpan_ke_sheets("Crypto", crypto, data_harga, hasil, indikator)
            
            # Catat ke performance tracker
            if analysis_data.get("sinyal") != "HOLD":
                catat_sinyal(
                    "Crypto", crypto,
                    analysis_data["entry"],
                    analysis_data["sinyal"],
                    analysis_data["sl"],
                    analysis_data["tp"],
                    analysis_data.get("skor_detail")
                )
            
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

                print(f"\n⏳ Menghitung indikator teknikal {saham} (enhanced)...")
                indikator = get_stock_indicators(saham)
                if indikator:
                    print(f"✅ Indikator berhasil dihitung!")
                    print(f"   📈 RSI: {indikator['rsi']} → {indikator['rsi_status']}")
                    print(f"   📉 MACD: {indikator['macd_status']}")
                    print(f"   📊 Trend: {indikator['trend_status']} (MA50: {indikator.get('ma50', 'N/A')} | MA200: {indikator.get('ma200', 'N/A')})")
                    print(f"   📦 Volume: {indikator['volume_status']} (rasio: {indikator['volume_ratio']}x)")
                    print(f"   🏪 Market: {indikator['market_condition']}")
                else:
                    print("⚠️ Indikator tidak tersedia.")

                print(f"\n🤖 AI sedang menganalisis {saham} (10-Point System)...\n")
                hasil, analysis_data = analisis_ai_v2(saham, "Saham", data_harga, berita, indikator, modal)
                print("-" * 60)
                print(hasil)
                print("-" * 60)
                
                # Simpan
                simpan_ke_excel("Saham", saham, data_harga, "", hasil)
                simpan_ke_sheets("Saham", saham, data_harga, hasil, indikator)
                
                # Catat ke performance tracker
                if analysis_data.get("sinyal") != "HOLD":
                    catat_sinyal(
                        "Saham", saham,
                        analysis_data["entry"],
                        analysis_data["sinyal"],
                        analysis_data["sl"],
                        analysis_data["tp"],
                        analysis_data.get("skor_detail")
                    )
                    
            except Exception as e:
                if "403" in str(e) or "PermissionDenied" in str(type(e).__name__):
                    print(f"❌ API error - coba lagi atau gunakan VPN!")
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
            print("\n⏳ Menghitung performa bot...")
            performa = hitung_performa()
            if not performa:
                print("⚠️ Belum ada data performa!")
            else:
                print("\n" + "=" * 60)
                print("   📊 PERFORMA BOT")
                print("=" * 60)
                print(f"   📈 Total Sinyal : {performa['total_sinyal']}")
                print(f"   🟢 Open         : {performa['sinyal_open']}")
                print(f"   🔵 Closed       : {performa['sinyal_closed']}")
                print(f"   ✅ WIN          : {performa['wins']}")
                print(f"   ❌ LOSS         : {performa['losses']}")
                print(f"   🎯 Win Rate     : {performa['win_rate']}%")
                print(f"   💰 Avg Profit   : {performa['avg_profit']}%")
                print(f"   📉 Max Drawdown : {performa['max_drawdown']}%")
                print("=" * 60)
                
                # Opsi update sinyal
                update = input("\nUpdate sinyal tertentu? (y/n): ").lower()
                if update == "y":
                    nama = input("Masukkan nama aset (contoh: bitcoin / BBCA.JK): ")
                    print(f"⏳ Mengupdate sinyal {nama}...")
                    update_sinyal_closed(nama)

        elif pilihan == "7":
            print(f"\n💰 Modal saat ini: Rp {modal:,.0f}")
            try:
                modal_baru = float(input("Masukkan modal baru (dalam Rupiah): "))
                modal = modal_baru
                print(f"✅ Modal diubah menjadi Rp {modal:,.0f}")
            except:
                print("❌ Input tidak valid!")

        elif pilihan == "8":
            print("\nSampai jumpa! 👋")
            break
        else:
            print("❌ Pilihan tidak valid!")

if __name__ == "__main__":
    main()