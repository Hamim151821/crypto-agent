from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes
from dotenv import load_dotenv
import os
import sys
import time
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from main import get_crypto_price, get_stock_price, get_crypto_news, get_stock_news, get_crypto_indicators, get_stock_indicators, analisis_ai, alert_list, tambah_alert, simpan_alert

load_dotenv()
TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

# ==============================
# HELPER — Kirim pesan panjang
# ==============================
async def kirim_pesan_panjang(update, teks):
    maks = 4000
    if len(teks) <= maks:
        await update.message.reply_text(teks, parse_mode="Markdown")
    else:
        bagian = [teks[i:i+maks] for i in range(0, len(teks), maks)]
        for b in bagian:
            await update.message.reply_text(b, parse_mode="Markdown")
            time.sleep(0.5)

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
    keyboard = [
        [InlineKeyboardButton("📈 Analisis Crypto", callback_data="crypto")],
        [InlineKeyboardButton("📉 Analisis Saham", callback_data="saham")],
        [InlineKeyboardButton("🔔 Set Alert", callback_data="alert")],
        [InlineKeyboardButton("📋 Lihat Alert Aktif", callback_data="lihat_alert")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        "🤖 *CRYPTO & SAHAM AGENT*\n\nSelamat datang! Pilih menu:",
        parse_mode="Markdown",
        reply_markup=reply_markup
    )

# ==============================
# COMMAND /analisis
# ==============================
async def analisis_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text(
            "❌ Format salah!\n\nContoh:\n`/analisis bitcoin`\n`/analisis BBCA.JK`\n`/analisis AAPL`",
            parse_mode="Markdown"
        )
        return

    aset = context.args[0].strip()
    await update.message.reply_text(f"⏳ Mengambil data *{aset}*...", parse_mode="Markdown")

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
            indikator = get_crypto_indicators(aset)

        await update.message.reply_text(
            f"✅ Data berhasil diambil!\n🤖 AI sedang menganalisis *{aset}*...",
            parse_mode="Markdown"
        )

        hasil = analisis_ai(
            f"Berikan analisis lengkap untuk {aset}",
            data_harga, berita, indikator
        )

        # Simpan ke Google Sheets
        from main import simpan_ke_sheets, simpan_ke_excel
        simpan_ke_sheets(jenis, aset, data_harga, hasil, indikator)

        header = f"📊 *Analisis {aset.upper()}*\n\n"
        await kirim_pesan_panjang(update, header + hasil)

    except Exception as e:
        await update.message.reply_text(
            f"⚠️ Terjadi error saat menganalisis *{aset}*\nCoba beberapa saat lagi!",
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
    teks = """
🤖 *PANDUAN CRYPTO & SAHAM AGENT*

📌 *Perintah yang tersedia:*

`/start` → Menu utama
`/analisis [aset]` → Analisis harga & sinyal
`/alert [aset] [kondisi] [harga]` → Set alert harga
`/alerts` → Lihat semua alert aktif
`/help` → Tampilkan panduan ini

📌 *Contoh penggunaan:*

`/analisis bitcoin`
`/analisis ethereum`
`/analisis BBCA.JK`
`/analisis AAPL`
`/alert bitcoin naik 70000`
`/alert BBCA.JK turun 6000`

⚠️ _Analisis ini bukan saran investasi. Selalu lakukan riset sendiri!_
"""
    await update.message.reply_text(teks, parse_mode="Markdown")

# ==============================
# BUTTON HANDLER
# ==============================
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == "crypto":
        await query.message.reply_text(
            "📈 *Analisis Crypto*\n\nKetik perintah:\n`/analisis bitcoin`\n`/analisis ethereum`\n`/analisis solana`",
            parse_mode="Markdown"
        )
    elif query.data == "saham":
        await query.message.reply_text(
            "📉 *Analisis Saham*\n\nKetik perintah:\n`/analisis BBCA.JK`\n`/analisis BBRI.JK`\n`/analisis AAPL`",
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

# Performa

async def performa_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("⏳ Menghitung performa bot...")
    
    from main import hitung_performa, update_sinyal_closed
    
    # Update sinyal yang sudah closed dulu
    if context.args:
        update_sinyal_closed(context.args[0])
    
    performa = hitung_performa()
    
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
# JALANKAN BOT
# ==============================
def main():
    app = Application.builder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("analisis", analisis_cmd))
    app.add_handler(CommandHandler("alert", alert_cmd))
    app.add_handler(CommandHandler("alerts", alerts_cmd))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(CommandHandler("performa", performa_cmd))

    print("🤖 Telegram Bot berjalan...")
    app.run_polling()

if __name__ == "__main__":
    main()