from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes
from dotenv import load_dotenv
import os
import sys
import time
import traceback
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from main import (
    get_crypto_price, get_stock_price,
    get_crypto_news, get_stock_news,
    get_crypto_indicators, get_stock_indicators,
    analisis_ai_v2, analisis_ai,
    alert_list, tambah_alert, simpan_alert,
    simpan_ke_sheets, simpan_ke_excel, catat_sinyal,
    hitung_performa, update_sinyal_closed,
    DEFAULT_MODAL,
    get_sheets_client,
    get_fear_greed_index, get_binance_ticker, get_binance_depth,
    get_coingecko_market_ticker,
    get_money_flow_analysis, run_bsjp_screener,
)
from user_data import UserDataManager

load_dotenv()
TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

# Persistent user data manager
user_manager = UserDataManager()

# Bot metadata
BOT_VERSION = "2.3.0"
BOT_NAME = "Crypto & Saham Agent"

# ==============================
# HELPER — Kirim pesan panjang
# ==============================
async def kirim_pesan_panjang(update_or_message, teks):
    """Kirim pesan panjang, dipecah per 4000 karakter pada batas baris"""
    maks = 4000
    if len(teks) <= maks:
        bagian_list = [teks]
    else:
        bagian_list = []
        sisa = teks
        while len(sisa) > maks:
            # Cari newline terakhir sebelum batas 4000 karakter
            pos = sisa.rfind('\n', 0, maks)
            if pos == -1 or pos < maks // 2:
                pos = maks
            bagian_list.append(sisa[:pos])
            sisa = sisa[pos:].lstrip('\n')
        if sisa.strip():
            bagian_list.append(sisa)
    
    # Tentukan target reply
    if hasattr(update_or_message, 'message') and update_or_message.message:
        message = update_or_message.message
    elif hasattr(update_or_message, 'reply_text'):
        message = update_or_message
    else:
        message = update_or_message
    
    for b in bagian_list:
        try:
            await message.reply_text(b, parse_mode=None)
        except Exception:
            try:
                await message.reply_text(b)
            except:
                pass
        time.sleep(0.3)

# ==============================
# HELPER — Retry request
# ==============================
def retry(func, *args, max_retry=3, **kwargs):
    for i in range(max_retry):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            if i == max_retry - 1:
                raise e
            time.sleep(2)


# ==============================
# HELPER — Bangun baris data harga top crypto
# Coba Binance dulu, fallback ke CoinGecko
# ==============================
def build_market_pulse_lines():
    """
    Ambil harga real-time untuk BTC, ETH, SOL.
    Prioritas: Binance → CoinGecko fallback.
    Returns: (list_of_lines, source_label)
    """
    top_coins = [("bitcoin", "₿ BTC"), ("ethereum", "Ξ ETH"), ("solana", "◎ SOL")]
    binance_lines = []

    # Coba Binance
    for coin_id, coin_label in top_coins:
        ticker = get_binance_ticker(coin_id)
        depth = get_binance_depth(coin_id)
        if ticker:
            change_emoji = "🟢" if ticker["change_pct"] >= 0 else "🔴"
            line = f"{coin_label}: ${ticker['price']:,.2f} {change_emoji} {ticker['change_pct']:+.2f}%"
            if depth:
                line += f" | Buy:{depth['buy_pressure']}% Sell:{depth['sell_pressure']}%"
            binance_lines.append(line)

    if binance_lines:
        return binance_lines, "Binance"

    # Fallback ke CoinGecko
    print("⚠️ Binance tidak tersedia, fallback ke CoinGecko untuk market pulse...")
    cg_data = get_coingecko_market_ticker([c[0] for c in top_coins])
    cg_lines = []
    for coin_id, coin_label in top_coins:
        if coin_id in cg_data:
            price = cg_data[coin_id].get("price", 0)
            change = cg_data[coin_id].get("change_pct", 0)
            if price > 0:
                change_emoji = "🟢" if change >= 0 else "🔴"
                cg_lines.append(f"{coin_label}: ${price:,.2f} {change_emoji} {change:+.2f}%")

    return cg_lines, "CoinGecko"

# ==============================
# COMMAND /start
# ==============================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    remaining = user_manager.get_remaining_requests(user.id)

    keyboard = [
        [InlineKeyboardButton("📈 Analisis Crypto", callback_data="crypto"),
         InlineKeyboardButton("📉 Analisis Saham", callback_data="saham")],
        [InlineKeyboardButton("🌡️ Market Pulse", callback_data="sentiment"),
         InlineKeyboardButton("📋 Histori Saya", callback_data="histori")],
        [InlineKeyboardButton("📊 Performa Saya", callback_data="performa"),
         InlineKeyboardButton("🔔 Set Alert", callback_data="alert")],
        [InlineKeyboardButton("💸 Money Flow", callback_data="moneyflow"),
         InlineKeyboardButton("🔍 BSJP Screener", callback_data="bsjp")],
        [InlineKeyboardButton("💰 Set Modal", callback_data="set_modal"),
         InlineKeyboardButton("ℹ️ Tentang Bot", callback_data="about")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        f"━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"🤖  *{BOT_NAME} v{BOT_VERSION}*\n"
        f"   _10-Point Analysis System_\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"Selamat datang! 👋\n\n"
        f"Bot ini menganalisis crypto & saham secara gratis menggunakan:\n"
        f"• 10 Indikator Teknikal (RSI, MACD, Bollinger, dll)\n"
        f"• AI-Powered Narrative & Scoring\n"
        f"• 💸 Money Flow & Bandarmology (MFI, CMF, Net Foreign)\n"
        f"• 🔍 BSJP Screener — scan 40 saham LQ45 otomatis\n\n"
        f"📊 Sisa kuota: *{remaining} analisis/jam*\n"
        f"💡 Ketik `/analisis bitcoin` untuk mulai!\n\n"
        f"Pilih menu di bawah:",
        parse_mode="Markdown",
        reply_markup=reply_markup
    )

# ==============================
# COMMAND /analisis — 10-Point System
# ==============================
async def analisis_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text(
            "❌ Format salah!\n\nContoh:\n`/analisis bitcoin`\n`/analisis BBCA.JK`\n`/analisis AAPL`",
            parse_mode="Markdown"
        )
        return

    user_id = update.effective_user.id

    # ── Rate Limit Check ──
    allowed, limit_msg = user_manager.check_rate_limit(user_id)
    if not allowed:
        await update.message.reply_text(limit_msg)
        return

    aset = context.args[0].strip()
    modal = user_manager.get_modal(user_id)
    remaining = user_manager.get_remaining_requests(user_id)
    
    await update.message.reply_text(
        f"⏳ Mengambil data *{aset}*...\n"
        f"💰 Modal: Rp {modal:,.0f} | Sisa kuota: {remaining}",
        parse_mode="Markdown"
    )

    try:
        # Tentukan jenis aset
        if "." in aset or aset.upper() == aset:
            aset = aset.upper()
            jenis = "Saham"
            
            # Ambil data dengan retry
            try:
                data_harga = retry(get_stock_price, aset)
            except:
                await update.message.reply_text(
                    f"❌ Saham *{aset}* tidak ditemukan!\n\nPastikan format benar:\n• Saham Indonesia: `BBCA.JK`\n• Saham US: `AAPL`",
                    parse_mode="Markdown"
                )
                return

            berita = get_stock_news(aset)
            
            await update.message.reply_text(
                f"⏳ Menghitung indikator teknikal *{aset}* (enhanced)...",
                parse_mode="Markdown"
            )
            indikator = get_stock_indicators(aset)

        else:
            aset = aset.lower()
            jenis = "Crypto"

            # Ambil data dengan retry
            try:
                data_harga = retry(get_crypto_price, aset)
                if not data_harga or aset not in data_harga:
                    raise ValueError("Crypto tidak ditemukan")
            except:
                await update.message.reply_text(
                    f"❌ Crypto *{aset}* tidak ditemukan!\n\nContoh yang benar:\n• `bitcoin`\n• `ethereum`\n• `solana`\n• `dogecoin`",
                    parse_mode="Markdown"
                )
                return

            berita = get_crypto_news(aset)
            
            await update.message.reply_text(
                f"⏳ Menghitung indikator teknikal *{aset}* (enhanced)...",
                parse_mode="Markdown"
            )
            indikator = get_crypto_indicators(aset)

        await update.message.reply_text(
            f"✅ Data berhasil diambil!\n🤖 AI sedang menganalisis *{aset}* (10-Point System)...",
            parse_mode="Markdown"
        )

        # === PANGGIL ANALISIS V2 ===
        hasil, analysis_data = analisis_ai_v2(
            aset, jenis, data_harga, berita, indikator, modal
        )

        # Record request SETELAH berhasil
        user_manager.record_request(user_id)

        # Kirim hasil analisis
        await kirim_pesan_panjang(update, hasil)

        # Simpan ke Google Sheets (setelah pesan terkirim)
        try:
            simpan_ke_sheets(jenis, aset, data_harga, hasil, indikator, user_id=user_id)

            # Catat sinyal ke Performance sheet
            if analysis_data.get("sinyal") != "HOLD":
                catat_sinyal(
                    jenis, aset,
                    analysis_data["entry"],
                    analysis_data["sinyal"],
                    analysis_data["sl"],
                    analysis_data["tp"],
                    analysis_data.get("skor_detail"),
                    user_id=user_id
                )
        except Exception as e:
            print(f"⚠️ Gagal simpan/catat performa: {e}")

    except Exception as e:
        print(f"❌ ERROR analisis {aset}: {type(e).__name__}: {e}")
        try:
            await update.message.reply_text(
                f"⚠️ Terjadi gangguan saat menganalisis *{aset}*.\n\n"
                f"Kemungkinan penyebab:\n"
                f"• Server data sedang sibuk\n"
                f"• Nama aset salah ketik\n\n"
                f"💡 Coba lagi dalam beberapa saat!",
                parse_mode="Markdown"
            )
        except:
            await update.message.reply_text(f"⚠️ Error saat analisis. Coba lagi nanti!")

# ==============================
# COMMAND /modal
# ==============================
async def modal_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    if not context.args:
        current = user_manager.get_modal(user_id)
        await update.message.reply_text(
            f"💰 *Modal kamu saat ini:* Rp {current:,.0f}\n\n"
            f"Untuk mengubah, ketik:\n`/modal 5000000`\n\n"
            f"Contoh:\n"
            f"• `/modal 1000000` → Rp 1.000.000\n"
            f"• `/modal 10000000` → Rp 10.000.000\n"
            f"• `/modal 50000000` → Rp 50.000.000",
            parse_mode="Markdown"
        )
        return
    
    try:
        modal_baru = float(context.args[0].replace(".", "").replace(",", ""))
        if modal_baru <= 0:
            raise ValueError("Modal harus positif")
        
        user_manager.set_modal(user_id, modal_baru)
        await update.message.reply_text(
            f"✅ *Modal berhasil diubah!*\n\n"
            f"💰 Modal baru: Rp {modal_baru:,.0f}\n"
            f"📊 Risk per trade: Rp {modal_baru * 0.01:,.0f} (1%)",
            parse_mode="Markdown"
        )
    except ValueError:
        await update.message.reply_text(
            "❌ Format salah! Masukkan angka.\n\nContoh: `/modal 5000000`",
            parse_mode="Markdown"
        )

# ==============================
# COMMAND /alert
# ==============================
async def alert_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) < 3:
        await update.message.reply_text(
            "❌ Format salah!\n\nContoh:\n`/alert bitcoin naik 70000`\n`/alert BBCA.JK turun 6000`",
            parse_mode="Markdown"
        )
        return

    try:
        nama = context.args[0].strip()
        kondisi = context.args[1].lower().strip()
        harga_target = float(context.args[2])

        if kondisi not in ["naik", "turun"]:
            await update.message.reply_text(
                "❌ Kondisi harus `naik` atau `turun`!",
                parse_mode="Markdown"
            )
            return

        if "." in nama or nama.upper() == nama:
            jenis = "saham"
            nama = nama.upper()
        else:
            jenis = "crypto"
            nama = nama.lower()

        tambah_alert(jenis, nama, harga_target, kondisi)
        await update.message.reply_text(
            f"✅ *Alert ditambahkan!*\n\n📌 Aset: {nama}\n📊 Kondisi: {kondisi}\n💰 Target: {harga_target:,}",
            parse_mode="Markdown"
        )

    except ValueError:
        await update.message.reply_text(
            "❌ Harga target harus berupa angka!\nContoh: `/alert bitcoin naik 70000`",
            parse_mode="Markdown"
        )

# ==============================
# COMMAND /alerts
# ==============================
async def alerts_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not alert_list:
        await update.message.reply_text("⚠️ Tidak ada alert aktif saat ini!")
        return

    teks = "📋 *Alert Aktif:*\n\n"
    for i, a in enumerate(alert_list, 1):
        teks += f"{i}. *{a['nama_aset']}* → {a['kondisi']} `{a['harga_target']:,}`\n"

    await update.message.reply_text(teks, parse_mode="Markdown")

# ==============================
# COMMAND /help
# ==============================
async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    teks = f"""
🤖 *PANDUAN {BOT_NAME.upper()} v{BOT_VERSION}*
_(10-Point Analysis System)_

📌 *Perintah yang tersedia:*

`/start` → Menu utama
`/analisis [aset]` → Analisis harga & sinyal (10-Point)
`/sentiment` → Sentimen pasar crypto (Fear & Greed)
`/moneyflow [kode.JK]` → Analisis Money Flow & Bandarmology
`/bsjp` → Screener Beli Sore Jual Pagi (BSJP)
`/histori` → Riwayat analisis kamu
`/performa [aset]` → Lihat & update performa
`/modal [jumlah]` → Set modal trading
`/alert [aset] [kondisi] [harga]` → Set alert harga
`/alerts` → Lihat semua alert aktif
`/about` → Tentang bot & developer
`/help` → Tampilkan panduan ini

📌 *Contoh penggunaan:*

`/analisis bitcoin`
`/analisis BBCA.JK`
`/moneyflow BBRI.JK`
`/bsjp`
`/modal 5000000`
`/alert bitcoin naik 70000`

📊 *Fitur Unggulan:*
• 10-Point Scoring System
• Money Flow Index (MFI) & Chaikin Money Flow (CMF)
• Net Foreign Buy/Sell dari IDX (Bandarmology)
• BSJP Screener — scan 40 saham LQ45 otomatis
• Fear & Greed Index
• Harga real-time (Binance / CoinGecko fallback)

📊 *Kuota:* {user_manager.get_remaining_requests(update.effective_user.id)} analisis tersisa (reset tiap jam)

⚠️ _Analisis ini bukan saran investasi. Selalu lakukan riset sendiri!_
"""
    await update.message.reply_text(teks, parse_mode="Markdown")

# ==============================
# COMMAND /about
# ==============================
async def about_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    total_users = user_manager.get_total_users()
    total_analyses = user_manager.get_total_analyses()

    teks = f"""
━━━━━━━━━━━━━━━━━━━━━━━━━
ℹ️  *TENTANG {BOT_NAME.upper()}*
━━━━━━━━━━━━━━━━━━━━━━━━━

📌 *Versi:* {BOT_VERSION}
🏗️ *Developer:* Hamim
🔗 *GitHub:* [crypto-agent](https://github.com/Hamim151821/crypto-agent)

🛠️ *Tech Stack:*
• Python 3 + python-telegram-bot
• OpenRouter AI (Meta Llama 3.3 70B)
• CoinGecko API (Crypto Data)
• Binance API (Real-Time Price & Order Book)
• Fear & Greed Index (Market Sentiment)
• Yahoo Finance API (Saham)
• Google Sheets (Data Logging)
• 10-Point Deterministic Scoring Engine

📊 *Statistik Bot:*
• Total Pengguna: {total_users}
• Total Analisis: {total_analyses}

💡 *Fitur Unggulan:*
• Analisis teknikal 10 indikator
• AI-powered narrative & reasoning
• Smart position sizing & risk management
• Adaptive learning dari trade history
• Support crypto & saham global
• Fear & Greed Index (sentimen pasar crypto)
• Binance real-time price & order book depth

🆓 Bot ini sepenuhnya *GRATIS* dan open-source.
Dibuat sebagai proyek portofolio untuk menunjukkan kemampuan di bidang AI, data engineering, dan financial technology.

⚠️ _Bukan nasihat keuangan. Selalu lakukan riset sendiri (DYOR)._
"""
    await update.message.reply_text(teks, parse_mode="Markdown", disable_web_page_preview=True)

# ==============================
# BUTTON HANDLER
# ==============================
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == "crypto":
        keyboard = [
            [InlineKeyboardButton("₿ Bitcoin", callback_data="q_bitcoin"),
             InlineKeyboardButton("Ξ Ethereum", callback_data="q_ethereum")],
            [InlineKeyboardButton("◎ Solana", callback_data="q_solana"),
             InlineKeyboardButton("🐕 Dogecoin", callback_data="q_dogecoin")],
            [InlineKeyboardButton("🔷 Cardano", callback_data="q_cardano"),
             InlineKeyboardButton("✕ Ripple", callback_data="q_ripple")],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.message.reply_text(
            "📈 *Analisis Crypto (10-Point System)*\n\n"
            "Pilih aset populer di bawah, atau ketik manual:\n"
            "`/analisis bitcoin`\n`/analisis ethereum`",
            parse_mode="Markdown",
            reply_markup=reply_markup
        )

    elif query.data == "saham":
        keyboard = [
            [InlineKeyboardButton("🏦 BBCA", callback_data="q_BBCA.JK"),
             InlineKeyboardButton("🏦 BBRI", callback_data="q_BBRI.JK")],
            [InlineKeyboardButton("📡 TLKM", callback_data="q_TLKM.JK"),
             InlineKeyboardButton("🚗 ASII", callback_data="q_ASII.JK")],
            [InlineKeyboardButton("🍎 AAPL", callback_data="q_AAPL"),
             InlineKeyboardButton("⚡ NVDA", callback_data="q_NVDA")],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.message.reply_text(
            "📉 *Analisis Saham (10-Point System)*\n\n"
            "Pilih saham populer di bawah, atau ketik manual:\n"
            "`/analisis BBCA.JK`\n`/analisis AAPL`",
            parse_mode="Markdown",
            reply_markup=reply_markup
        )

    elif query.data.startswith("q_"):
        # Quick-access: jalankan analisis langsung
        aset = query.data[2:]  # Hapus prefix "q_"
        user_id = query.from_user.id

        # Rate limit check
        allowed, limit_msg = user_manager.check_rate_limit(user_id)
        if not allowed:
            await query.message.reply_text(limit_msg)
            return

        modal = user_manager.get_modal(user_id)

        # Tentukan jenis
        if "." in aset or aset.upper() == aset:
            aset_display = aset.upper()
            jenis = "Saham"
        else:
            aset_display = aset.lower()
            jenis = "Crypto"

        await query.message.reply_text(
            f"⏳ Mengambil data *{aset_display}*...\n💰 Modal: Rp {modal:,.0f}",
            parse_mode="Markdown"
        )

        try:
            if jenis == "Crypto":
                aset = aset.lower()
                data_harga = retry(get_crypto_price, aset)
                if not data_harga or aset not in data_harga:
                    await query.message.reply_text(f"❌ Crypto *{aset}* tidak ditemukan!", parse_mode="Markdown")
                    return
                berita = get_crypto_news(aset)
                indikator = get_crypto_indicators(aset)
            else:
                aset = aset.upper()
                data_harga = retry(get_stock_price, aset)
                if not data_harga:
                    await query.message.reply_text(f"❌ Saham *{aset}* tidak ditemukan!", parse_mode="Markdown")
                    return
                berita = get_stock_news(aset)
                indikator = get_stock_indicators(aset)

            await query.message.reply_text(
                f"🤖 AI sedang menganalisis *{aset_display}*...",
                parse_mode="Markdown"
            )

            hasil, analysis_data = analisis_ai_v2(aset, jenis, data_harga, berita, indikator, modal)

            user_manager.record_request(user_id)
            await kirim_pesan_panjang(query.message, hasil)

            try:
                simpan_ke_sheets(jenis, aset, data_harga, hasil, indikator, user_id=query.from_user.id)
                if analysis_data.get("sinyal") != "HOLD":
                    catat_sinyal(jenis, aset, analysis_data["entry"], analysis_data["sinyal"],
                                analysis_data["sl"], analysis_data["tp"], analysis_data.get("skor_detail"),
                                user_id=query.from_user.id)
            except Exception as e:
                print(f"⚠️ Gagal simpan: {e}")

        except Exception as e:
            print(f"❌ ERROR quick-analisis {aset}: {e}")
            await query.message.reply_text(
                f"⚠️ Gagal menganalisis *{aset_display}*. Coba lagi nanti!",
                parse_mode="Markdown"
            )

    elif query.data == "alert":
        await query.message.reply_text(
            "🔔 *Set Alert Harga*\n\nFormat:\n`/alert [aset] [naik/turun] [harga]`\n\nContoh:\n`/alert bitcoin naik 70000`\n`/alert BBCA.JK turun 6000`",
            parse_mode="Markdown"
        )
    elif query.data == "lihat_alert":
        if not alert_list:
            await query.message.reply_text("⚠️ Tidak ada alert aktif saat ini!")
        else:
            teks = "📋 *Alert Aktif:*\n\n"
            for i, a in enumerate(alert_list, 1):
                teks += f"{i}. *{a['nama_aset']}* → {a['kondisi']} `{a['harga_target']:,}`\n"
            await query.message.reply_text(teks, parse_mode="Markdown")
    elif query.data == "performa":
        await query.message.reply_text("⏳ Menghitung performa kamu...")
        performa = hitung_performa(user_id=query.from_user.id)
        if not performa:
            await query.message.reply_text("⚠️ Belum ada data performa!\n\nData performa akan muncul setelah kamu melakukan analisis dan bot mencatat sinyal BELI/JUAL.")
        else:
            teks = f"""
📊 *PERFORMA BOT*

📈 Total Sinyal: {performa['total_sinyal']}
🟢 Open: {performa['sinyal_open']}
🔵 Closed: {performa['sinyal_closed']}

✅ WIN: {performa['wins']}
❌ LOSS: {performa['losses']}
🎯 Win Rate: *{performa['win_rate']}%*

💰 Avg Profit: {performa['avg_profit']}%
📉 Max Drawdown: {performa['max_drawdown']}%

_Gunakan /performa [aset] untuk update sinyal tertentu_
"""
            await query.message.reply_text(teks, parse_mode="Markdown")
    elif query.data == "set_modal":
        user_id = query.from_user.id
        current = user_manager.get_modal(user_id)
        await query.message.reply_text(
            f"💰 *Modal kamu saat ini:* Rp {current:,.0f}\n\n"
            f"Untuk mengubah, ketik:\n`/modal [jumlah]`\n\n"
            f"Contoh: `/modal 5000000`",
            parse_mode="Markdown"
        )
    elif query.data == "about":
        total_users = user_manager.get_total_users()
        total_analyses = user_manager.get_total_analyses()
        await query.message.reply_text(
            f"━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"ℹ️  *TENTANG {BOT_NAME.upper()}*\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"📌 Versi: {BOT_VERSION}\n"
            f"🏗️ Developer: Hamim\n"
            f"🔗 GitHub: [crypto-agent](https://github.com/Hamim151821/crypto-agent)\n\n"
            f"📊 Pengguna: {total_users} | Analisis: {total_analyses}\n\n"
            f"🆓 Bot ini sepenuhnya *GRATIS* dan open-source.\n"
            f"⚠️ _Bukan nasihat keuangan. DYOR._",
            parse_mode="Markdown",
            disable_web_page_preview=True
        )
    elif query.data == "sentiment":
        # Inline sentiment — panggil Market Pulse langsung
        await query.message.reply_text("⏳ Mengambil data sentimen pasar crypto...")
        try:
            fng = get_fear_greed_index()
            if fng:
                fng_val = fng.get("value", 50)
                fng_label = fng.get("label", "Neutral")
                if fng_val <= 24:
                    fng_emoji = "😱"
                    fng_advice = "Pasar sangat takut → Sering jadi peluang beli (contrarian)."
                elif fng_val <= 49:
                    fng_emoji = "😰"
                    fng_advice = "Pasar masih khawatir → Hati-hati, tapi pantau peluang."
                elif fng_val <= 74:
                    fng_emoji = "😏"
                    fng_advice = "Pasar optimis → Momentum bagus, tapi jangan serakah."
                else:
                    fng_emoji = "🤑"
                    fng_advice = "Pasar sangat serakah → Waspada koreksi/dump!"
                filled = round(fng_val / 10)
                bar = "█" * filled + "░" * (10 - filled)
                fng_text = (
                    f"🌡️ *Fear & Greed Index*\n"
                    f"{fng_emoji} *{fng_val}/100* — {fng_label}\n"
                    f"[{bar}]\n"
                    f"💡 {fng_advice}\n"
                )
            else:
                fng_text = "🌡️ Fear & Greed: Data tidak tersedia\n"

            # Harga real-time (Binance atau CoinGecko fallback)
            pulse_lines, pulse_source = build_market_pulse_lines()
            if pulse_lines:
                binance_text = f"\n📊 *Harga Real-Time ({pulse_source})*\n" + "\n".join(pulse_lines) + "\n"
            else:
                binance_text = "\n📊 Data harga tidak tersedia\n"

            teks = (
                f"━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                f"🌡️  *CRYPTO MARKET PULSE*\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                f"{fng_text}\n"
                f"{binance_text}\n"
                f"💡 Gunakan `/analisis bitcoin` untuk analisis lengkap!\n\n"
                f"_Data dari alternative.me & {pulse_source} (gratis, real-time)_"
            )
            await query.message.reply_text(teks, parse_mode="Markdown")
        except Exception as e:
            print(f"❌ Error sentiment button: {type(e).__name__}: {e}")
            await query.message.reply_text("⚠️ Gagal mengambil data sentimen. Coba lagi nanti!")
    elif query.data == "histori":
        # Inline histori — langsung panggil logic yang sama dengan /histori
        user_id = query.from_user.id
        await query.message.reply_text("⏳ Mengambil histori analisis kamu...")

        try:
            gc = get_sheets_client()
            if not gc:
                await query.message.reply_text(
                    "⚠️ Gagal terhubung ke Google Sheets.\n\n"
                    "Kemungkinan penyebab:\n"
                    "• Kredensial Google belum dikonfigurasi\n"
                    "• Koneksi internet bermasalah\n\n"
                    "💡 Coba lagi dalam beberapa saat."
                )
                return

            sheet_id = os.getenv("GOOGLE_SHEETS_ID")
            if not sheet_id:
                await query.message.reply_text("⚠️ Google Sheets ID belum dikonfigurasi.")
                return

            spreadsheet = gc.open_by_key(sheet_id)

            try:
                ws = spreadsheet.worksheet("Histori")
            except Exception:
                await query.message.reply_text(
                    "⚠️ Belum ada data histori!\n\n"
                    "Histori akan tersedia setelah kamu melakukan analisis pertama.\n"
                    "💡 Coba `/analisis bitcoin` untuk memulai!",
                    parse_mode="Markdown"
                )
                return

            all_values = ws.get_all_values()
            if len(all_values) < 2:
                await query.message.reply_text(
                    "⚠️ Belum ada data histori!\n\n"
                    "💡 Coba `/analisis bitcoin` untuk memulai!",
                    parse_mode="Markdown"
                )
                return

            headers = all_values[0]
            data_rows = all_values[1:]
            uid_str = str(user_id)

            # Smart header detection: cek apakah baris pertama adalah header atau data
            # Jika tidak ada keyword header, anggap semua baris adalah data (tanpa header)
            HEADER_KEYWORDS = {"User ID", "Tanggal & Waktu", "Tanggal", "Nama Aset", "Sinyal AI"}
            has_header = any(kw in headers for kw in HEADER_KEYWORDS)
            if not has_header:
                # Tidak ada header row — gunakan posisi default sesuai skema simpan_ke_sheets
                # Schema: [Tanggal & Waktu(0), User ID(1), Jenis(2), Nama Aset(3),
                #          Harga(4), RSI(5), MACD(6), Sinyal AI(7), Analisis(8)]
                data_rows = all_values  # Semua row adalah data
                uid_col = 1
                tanggal_col = 0
                jenis_col = 2
                aset_col = 3
                sinyal_col = 7
            else:
                col_map = {h: i for i, h in enumerate(headers)}
                uid_col = col_map.get("User ID", 1)
                tanggal_col = col_map.get("Tanggal & Waktu", col_map.get("Tanggal", 0))
                jenis_col = col_map.get("Jenis", 2)
                aset_col = col_map.get("Nama Aset", col_map.get("Aset", 3))
                sinyal_col = col_map.get("Sinyal AI", col_map.get("Sinyal", 7))

            # Filter rows milik user ini
            user_rows = []
            for row in data_rows:
                if uid_col < len(row) and row[uid_col] == uid_str:
                    user_rows.append(row)

            if not user_rows:
                await query.message.reply_text(
                    "⚠️ Kamu belum memiliki histori analisis.\n\n"
                    "💡 Coba `/analisis bitcoin` untuk memulai!",
                    parse_mode="Markdown"
                )
                return

            recent = user_rows[-10:]
            teks = f"📋 *Histori Analisis Kamu* (terakhir {len(recent)} dari {len(user_rows)} total)\n\n"

            for idx, row in enumerate(reversed(recent), 1):
                tanggal = row[tanggal_col] if tanggal_col < len(row) else "-"
                jenis_val = row[jenis_col] if jenis_col < len(row) else "-"
                aset = row[aset_col] if aset_col < len(row) else "-"
                sinyal = row[sinyal_col] if sinyal_col < len(row) else "-"
                emoji = "📈" if jenis_val == "Crypto" else "📉"
                teks += f"{idx}. {emoji} *{aset}* | {sinyal} | {tanggal}\n"

            teks += f"\n_Total analisis: {len(user_rows)}_"
            await query.message.reply_text(teks, parse_mode="Markdown")

        except Exception as e:
            print(f"❌ Error histori button: {type(e).__name__}: {e}")
            traceback.print_exc()
            await query.message.reply_text(
                f"⚠️ Gagal mengambil histori.\n\n"
                f"Error: {type(e).__name__}\n"
                f"Coba lagi dalam beberapa saat!"
            )

    elif query.data == "moneyflow":
        await query.message.reply_text(
            "💸 *Money Flow Analysis*\n\n"
            "Masukkan kode saham IDX yang ingin dianalisis:\n"
            "`/moneyflow BBCA.JK`\n`/moneyflow BBRI.JK`\n\n"
            "Atau pilih saham populer:",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🏦 BBCA", callback_data="mf_BBCA.JK"),
                 InlineKeyboardButton("🏦 BBRI", callback_data="mf_BBRI.JK")],
                [InlineKeyboardButton("🏦 BMRI", callback_data="mf_BMRI.JK"),
                 InlineKeyboardButton("📡 TLKM", callback_data="mf_TLKM.JK")],
                [InlineKeyboardButton("🚗 ASII", callback_data="mf_ASII.JK"),
                 InlineKeyboardButton("💰 ADRO", callback_data="mf_ADRO.JK")],
            ])
        )

    elif query.data.startswith("mf_"):
        kode = query.data[3:]
        await _handle_moneyflow(query.message, kode)

    elif query.data == "bsjp":
        await _handle_bsjp_screener(query.message)

# ==============================
# COMMAND /performa
# ==============================
async def performa_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("⏳ Menghitung performa kamu...")
    
    user_id = update.effective_user.id

    # Update sinyal yang sudah closed dulu
    if context.args:
        update_sinyal_closed(context.args[0], user_id=user_id)
    
    performa = hitung_performa(user_id=user_id)
    
    if not performa:
        await update.message.reply_text("⚠️ Belum ada data performa!")
        return
    
    teks = f"""
📊 *PERFORMA BOT*

📈 Total Sinyal: {performa['total_sinyal']}
🟢 Open: {performa['sinyal_open']}
🔵 Closed: {performa['sinyal_closed']}

✅ WIN: {performa['wins']}
❌ LOSS: {performa['losses']}
🎯 Win Rate: *{performa['win_rate']}%*

💰 Avg Profit: {performa['avg_profit']}%
📉 Max Drawdown: {performa['max_drawdown']}%
"""
    await update.message.reply_text(teks, parse_mode="Markdown")

# ==============================
# COMMAND /histori
# ==============================
async def histori_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Tampilkan histori analisis milik user ini dari Google Sheets"""
    user_id = update.effective_user.id
    await update.message.reply_text("⏳ Mengambil histori analisis kamu...")

    try:
        gc = get_sheets_client()
        if not gc:
            await update.message.reply_text(
                "⚠️ Gagal terhubung ke Google Sheets.\n\n"
                "Kemungkinan penyebab:\n"
                "• Kredensial Google belum dikonfigurasi\n"
                "• Koneksi internet bermasalah\n\n"
                "💡 Coba lagi dalam beberapa saat."
            )
            return

        sheet_id = os.getenv("GOOGLE_SHEETS_ID")
        if not sheet_id:
            await update.message.reply_text("⚠️ Google Sheets ID belum dikonfigurasi.")
            return

        spreadsheet = gc.open_by_key(sheet_id)

        try:
            ws = spreadsheet.worksheet("Histori")
        except Exception:
            await update.message.reply_text(
                "⚠️ Belum ada data histori!\n\n"
                "Histori akan tersedia setelah kamu melakukan analisis pertama.\n"
                "💡 Coba `/analisis bitcoin` untuk memulai!",
                parse_mode="Markdown"
            )
            return

        all_values = ws.get_all_values()
        if len(all_values) < 1:
            await update.message.reply_text(
                "⚠️ Belum ada data histori!\n\n"
                "💡 Coba `/analisis bitcoin` untuk memulai!",
                parse_mode="Markdown"
            )
            return

        headers = all_values[0]
        uid_str = str(user_id)

        # Smart header detection
        HEADER_KEYWORDS = {"User ID", "Tanggal & Waktu", "Tanggal", "Nama Aset", "Sinyal AI"}
        has_header = any(kw in headers for kw in HEADER_KEYWORDS)
        if not has_header:
            # Tidak ada header row — gunakan posisi default
            data_rows = all_values
            uid_col = 1
            tanggal_col = 0
            jenis_col = 2
            aset_col = 3
            sinyal_col = 7
        else:
            data_rows = all_values[1:]
            col_map = {h: i for i, h in enumerate(headers)}
            uid_col = col_map.get("User ID", 1)
            tanggal_col = col_map.get("Tanggal & Waktu", col_map.get("Tanggal", 0))
            jenis_col = col_map.get("Jenis", 2)
            aset_col = col_map.get("Nama Aset", col_map.get("Aset", 3))
            sinyal_col = col_map.get("Sinyal AI", col_map.get("Sinyal", 7))

        # Filter by user_id
        user_rows = []
        for row in data_rows:
            if uid_col < len(row) and row[uid_col] == uid_str:
                user_rows.append(row)

        if not user_rows:
            await update.message.reply_text(
                "⚠️ Kamu belum memiliki histori analisis.\n\n"
                "💡 Coba `/analisis bitcoin` untuk memulai!",
                parse_mode="Markdown"
            )
            return

        # Tampilkan 10 histori terakhir
        recent = user_rows[-10:]
        teks = f"📋 *Histori Analisis Kamu* (terakhir {len(recent)} dari {len(user_rows)} total)\n\n"

        for idx, row in enumerate(reversed(recent), 1):
            tanggal = row[tanggal_col] if tanggal_col < len(row) else "-"
            jenis = row[jenis_col] if jenis_col < len(row) else "-"
            aset = row[aset_col] if aset_col < len(row) else "-"
            sinyal = row[sinyal_col] if sinyal_col < len(row) else "-"
            emoji = "📈" if jenis == "Crypto" else "📉"
            teks += f"{idx}. {emoji} *{aset}* | {sinyal} | {tanggal}\n"

        teks += f"\n_Total analisis: {len(user_rows)}_"
        await update.message.reply_text(teks, parse_mode="Markdown")

    except Exception as e:
        print(f"❌ Error histori: {type(e).__name__}: {e}")
        traceback.print_exc()
        await update.message.reply_text(
            f"⚠️ Gagal mengambil histori.\n\n"
            f"Error: {type(e).__name__}\n"
            f"Coba lagi dalam beberapa saat!"
        )

# ==============================
# COMMAND /sentiment — Quick Market Pulse
# ==============================

# ============================================================
# HELPER — Money Flow (dipakai dari button & command)
# ============================================================
async def _handle_moneyflow(message, kode_saham):
    kode_up = kode_saham.upper()
    if not kode_up.endswith(".JK"):
        kode_up = kode_up + ".JK"

    await message.reply_text(f"⏳ Menganalisis money flow {kode_up}...")

    try:
        mf = get_money_flow_analysis(kode_up)
        if not mf:
            await message.reply_text(
                f"⚠️ Tidak bisa mengambil data untuk *{kode_up}*.\n"
                f"Pastikan kode saham benar (contoh: `BBCA.JK`)",
                parse_mode="Markdown"
            )
            return

        # Format value transaksi ke miliar
        def rp_miliar(val):
            if val >= 1_000_000_000_000:
                return f"Rp {val/1_000_000_000_000:.2f} T"
            elif val >= 1_000_000_000:
                return f"Rp {val/1_000_000_000:.1f} M"
            else:
                return f"Rp {val/1_000_000:.0f} Jt"

        foreign = mf.get("foreign")
        if foreign:
            net = foreign["net_foreign"]
            sign = "+" if net >= 0 else ""
            foreign_text = (
                f"\n🌍 *Net Foreign Flow (IDX)*\n"
                f"• Buy : {rp_miliar(foreign['foreign_buy'])}\n"
                f"• Sell: {rp_miliar(foreign['foreign_sell'])}\n"
                f"• Net : {sign}{rp_miliar(abs(net))} → {foreign['status']}\n"
                f"• 💡 {foreign['interpretasi']}\n"
            )
        else:
            foreign_text = "\n🌍 *Net Foreign Flow:* Data tidak tersedia\n"

        teks = (
            f"━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"💸 *MONEY FLOW — {kode_up}*\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"💰 *Value Transaksi*\n"
            f"• Hari ini : {rp_miliar(mf['value_today'])}\n"
            f"• Rata20hr : {rp_miliar(mf['value_avg_20d'])}\n"
            f"• Rasio    : {mf['value_ratio']}x → {mf['value_status']}\n\n"
            f"📊 *Indikator Volume*\n"
            f"• MFI (14) : {mf['mfi']} → {mf['mfi_label']}\n"
            f"• CMF (20) : {mf['cmf']:.4f} → {mf['cmf_label']}\n"
            f"• OBV 5hr  : {mf['obv_trend']}\n"
            f"• Vol Ratio: {mf['vol_ratio']}x {'🔥 SPIKE' if mf['vol_spike'] else '(normal)'}\n"
            f"{foreign_text}\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"🧠 *KESIMPULAN (Skor: {mf['skor']})*\n"
            f"{mf['kesimpulan']}\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"⚠️ _Bukan nasihat keuangan. DYOR._"
        )
        await kirim_pesan_panjang(message, teks)

    except Exception as e:
        print(f"❌ Error moneyflow: {e}")
        await message.reply_text(f"⚠️ Gagal analisis money flow: {type(e).__name__}")


# ============================================================
# HELPER — BSJP Screener (dipakai dari button & command)
# ============================================================
async def _handle_bsjp_screener(message):
    await message.reply_text(
        "⏳ *Menjalankan BSJP Screener...*\n\n"
        "Memindai 40 saham IDX berdasarkan:\n"
        "• Value & Volume Transaksi\n"
        "• MFI (Money Flow Index)\n"
        "• Pola Candle & Trend\n"
        "• Net Foreign Flow\n\n"
        "_Harap tunggu ~60 detik..._",
        parse_mode="Markdown"
    )
    try:
        hasil = run_bsjp_screener()

        if not hasil:
            await message.reply_text(
                "📭 *Tidak ada saham yang lolos kriteria BSJP hari ini.*\n\n"
                "Kemungkinan:\n"
                "• Pasar sedang sideways/bearish\n"
                "• Value & volume saham LQ45 sedang rendah\n\n"
                "💡 Coba lagi mendekati sesi sore (14.00–15.30 WIB).",
                parse_mode="Markdown"
            )
            return

        teks = (
            "━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "🔍 *BSJP SCREENER RESULT*\n"
            "Beli Sore Jual Pagi — Kandidat Terbaik\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        )

        for rank, d in enumerate(hasil, 1):
            def rp_m(v):
                if v >= 1_000_000_000_000:
                    return f"{v/1_000_000_000_000:.1f}T"
                return f"{v/1_000_000_000:.0f}M"

            alasan_str   = " | ".join(d["alasan"][:4])
            warning_str  = " | ".join(d["peringatan"][:2])

            teks += (
                f"#{rank} 🏅 *{d['kode']}* — Skor: {d['skor']}\n"
                f"💵 Harga: Rp {d['price']:,.0f} | MA20: Rp {d['ma20']:,.0f}\n"
                f"💸 Value: {rp_m(d['val_today'])} ({d['val_ratio']}x avg)\n"
                f"📊 Vol: {d['vol_ratio']}x | RSI: {d['rsi']} | MFI: {d['mfi']}\n"
                f"✅ {alasan_str}\n"
            )
            if warning_str:
                teks += f"⚠️ {warning_str}\n"
            teks += "\n"

        teks += (
            "━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "💡 *Cara pakai:*\n"
            "Beli di sesi sore (14.00–15.30 WIB)\n"
            "Target jual: Pre-market / Opening besok pagi\n"
            "Selalu pasang Stop Loss!\n\n"
            "⚠️ _Bukan nasihat keuangan. DYOR._"
        )
        await kirim_pesan_panjang(message, teks)

    except Exception as e:
        print(f"❌ Error BSJP screener: {e}")
        await message.reply_text(f"⚠️ Gagal menjalankan screener: {type(e).__name__}")


# ==============================
# COMMAND /moneyflow
# ==============================
async def moneyflow_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args
    if not args:
        await update.message.reply_text(
            "💸 *Money Flow Analysis*\n\n"
            "Gunakan: `/moneyflow [kode_saham]`\n\n"
            "Contoh:\n"
            "`/moneyflow BBCA.JK`\n"
            "`/moneyflow BBRI.JK`\n"
            "`/moneyflow TLKM.JK`",
            parse_mode="Markdown"
        )
        return
    kode = args[0]
    await _handle_moneyflow(update.message, kode)


# ==============================
# COMMAND /bsjp
# ==============================
async def bsjp_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _handle_bsjp_screener(update.message)


# ==============================
# COMMAND /sentiment
# ==============================
async def sentiment_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Tampilkan Fear & Greed Index + Binance data top crypto secara cepat"""
    await update.message.reply_text("⏳ Mengambil data sentimen pasar crypto...")

    try:
        # Fear & Greed Index
        fng = get_fear_greed_index()
        if fng:
            fng_val = fng.get("value", 50)
            fng_label = fng.get("label", "Neutral")
            if fng_val <= 24:
                fng_emoji = "😱"
                fng_advice = "Pasar sangat takut → Sering jadi peluang beli (contrarian)."
            elif fng_val <= 49:
                fng_emoji = "😰"
                fng_advice = "Pasar masih khawatir → Hati-hati, tapi pantau peluang."
            elif fng_val <= 74:
                fng_emoji = "😏"
                fng_advice = "Pasar optimis → Momentum bagus, tapi jangan serakah."
            else:
                fng_emoji = "🤑"
                fng_advice = "Pasar sangat serakah → Waspada koreksi/dump!"
            filled = round(fng_val / 10)
            bar = "█" * filled + "░" * (10 - filled)
            fng_text = (
                f"🌡️ *Fear & Greed Index*\n"
                f"{fng_emoji} *{fng_val}/100* — {fng_label}\n"
                f"[{bar}]\n"
                f"💡 {fng_advice}\n"
            )
        else:
            fng_text = "🌡️ Fear & Greed: Data tidak tersedia\n"

        # Harga real-time (Binance atau CoinGecko fallback)
        pulse_lines, pulse_source = build_market_pulse_lines()
        if pulse_lines:
            binance_text = f"\n📊 *Harga Real-Time ({pulse_source})*\n" + "\n".join(pulse_lines) + "\n"
        else:
            binance_text = "\n📊 Data harga tidak tersedia\n"

        teks = (
            f"━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"🌡️  *CRYPTO MARKET PULSE*\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"{fng_text}\n"
            f"{binance_text}\n"
            f"💡 Gunakan `/analisis bitcoin` untuk analisis lengkap!\n\n"
            f"_Data dari alternative.me & Binance (gratis, real-time)_"
        )
        await update.message.reply_text(teks, parse_mode="Markdown")

    except Exception as e:
        print(f"❌ Error sentiment: {type(e).__name__}: {e}")
        traceback.print_exc()
        await update.message.reply_text("⚠️ Gagal mengambil data sentimen. Coba lagi nanti!")

# ==============================
# JALANKAN BOT
# ==============================
def main():
    app = Application.builder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("analisis", analisis_cmd))
    app.add_handler(CommandHandler("modal", modal_cmd))
    app.add_handler(CommandHandler("alert", alert_cmd))
    app.add_handler(CommandHandler("alerts", alerts_cmd))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("about", about_cmd))
    app.add_handler(CommandHandler("performa", performa_cmd))
    app.add_handler(CommandHandler("histori", histori_cmd))
    app.add_handler(CommandHandler("sentiment", sentiment_cmd))
    app.add_handler(CommandHandler("moneyflow", moneyflow_cmd))
    app.add_handler(CommandHandler("bsjp", bsjp_cmd))
    app.add_handler(CallbackQueryHandler(button_handler))

    print(f"🤖 {BOT_NAME} v{BOT_VERSION} berjalan...")
    print(f"📊 Total users: {user_manager.get_total_users()} | Total analyses: {user_manager.get_total_analyses()}")
    app.run_polling()

if __name__ == "__main__":
    main()