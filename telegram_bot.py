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
    get_sheets_client
)
from user_data import UserDataManager

load_dotenv()
TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

# Persistent user data manager
user_manager = UserDataManager()

# Bot metadata
BOT_VERSION = "2.1.0"
BOT_NAME = "Crypto & Saham Agent"

# ==============================
# HELPER — Kirim pesan panjang
# ==============================
async def kirim_pesan_panjang(update_or_message, teks):
    """Kirim pesan panjang, dipecah per 4000 karakter"""
    maks = 4000
    bagian_list = [teks] if len(teks) <= maks else [teks[i:i+maks] for i in range(0, len(teks), maks)]
    
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
# COMMAND /start
# ==============================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    remaining = user_manager.get_remaining_requests(user.id)

    keyboard = [
        [InlineKeyboardButton("📈 Analisis Crypto", callback_data="crypto"),
         InlineKeyboardButton("📉 Analisis Saham", callback_data="saham")],
        [InlineKeyboardButton("📊 Performa Saya", callback_data="performa"),
         InlineKeyboardButton("📋 Histori Saya", callback_data="histori")],
        [InlineKeyboardButton("🔔 Set Alert", callback_data="alert"),
         InlineKeyboardButton("📋 Alert Aktif", callback_data="lihat_alert")],
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
        f"• Smart Risk Management & Position Sizing\n\n"
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
`/modal [jumlah]` → Set modal trading
`/alert [aset] [kondisi] [harga]` → Set alert harga
`/alerts` → Lihat semua alert aktif
`/performa [aset]` → Lihat & update performa
`/about` → Tentang bot & developer
`/help` → Tampilkan panduan ini

📌 *Contoh penggunaan:*

`/analisis bitcoin`
`/analisis ethereum`
`/analisis BBCA.JK`
`/analisis AAPL`
`/modal 5000000`
`/alert bitcoin naik 70000`

📊 *Fitur 10-Point System:*
• Adaptive Learning (belajar dari histori)
• Market Condition (Trending/Sideways/Volatile)
• Deterministic Scoring (konsisten & terukur)
• Copy Trading & Position Sizing
• No-Trade Zone Detection

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

            # Safe column lookup — gunakan dict agar tidak crash jika header berbeda
            col_map = {h: i for i, h in enumerate(headers)}
            uid_col = col_map.get("User ID", -1)
            tanggal_col = col_map.get("Tanggal & Waktu", col_map.get("Tanggal", 0))
            jenis_col = col_map.get("Jenis", -1)
            aset_col = col_map.get("Nama Aset", col_map.get("Aset", -1))
            sinyal_col = col_map.get("Sinyal AI", col_map.get("Sinyal", -1))

            # Filter rows milik user ini
            user_rows = []
            for row in data_rows:
                if uid_col >= 0 and uid_col < len(row) and row[uid_col] == uid_str:
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
                tanggal = row[tanggal_col] if tanggal_col >= 0 and tanggal_col < len(row) else "-"
                jenis_val = row[jenis_col] if jenis_col >= 0 and jenis_col < len(row) else "-"
                aset = row[aset_col] if aset_col >= 0 and aset_col < len(row) else "-"
                sinyal = row[sinyal_col] if sinyal_col >= 0 and sinyal_col < len(row) else "-"
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
        if len(all_values) < 2:
            await update.message.reply_text(
                "⚠️ Belum ada data histori!\n\n"
                "💡 Coba `/analisis bitcoin` untuk memulai!",
                parse_mode="Markdown"
            )
            return

        headers = all_values[0]
        data_rows = all_values[1:]

        # Safe column lookup — gunakan dict agar tidak crash jika header berbeda
        col_map = {h: i for i, h in enumerate(headers)}
        uid_col = col_map.get("User ID", -1)
        tanggal_col = col_map.get("Tanggal & Waktu", col_map.get("Tanggal", 0))
        jenis_col = col_map.get("Jenis", -1)
        aset_col = col_map.get("Nama Aset", col_map.get("Aset", -1))
        sinyal_col = col_map.get("Sinyal AI", col_map.get("Sinyal", -1))

        # Filter by user_id
        uid_str = str(user_id)
        user_rows = []
        for row in data_rows:
            if uid_col >= 0 and uid_col < len(row) and row[uid_col] == uid_str:
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
            tanggal = row[tanggal_col] if tanggal_col >= 0 and tanggal_col < len(row) else "-"
            jenis = row[jenis_col] if jenis_col >= 0 and jenis_col < len(row) else "-"
            aset = row[aset_col] if aset_col >= 0 and aset_col < len(row) else "-"
            sinyal = row[sinyal_col] if sinyal_col >= 0 and sinyal_col < len(row) else "-"
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
    app.add_handler(CallbackQueryHandler(button_handler))

    print(f"🤖 {BOT_NAME} v{BOT_VERSION} berjalan...")
    print(f"📊 Total users: {user_manager.get_total_users()} | Total analyses: {user_manager.get_total_analyses()}")
    app.run_polling()

if __name__ == "__main__":
    main()