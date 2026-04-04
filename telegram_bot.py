from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes
from dotenv import load_dotenv
import os
import sys
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from main import get_crypto_price, get_stock_price, get_crypto_news, get_stock_news, get_crypto_indicators, get_stock_indicators, analisis_ai, alert_list, tambah_alert, simpan_alert

load_dotenv()
TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

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
# COMMAND /crypto
# ==============================
async def crypto_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Ketik nama crypto:\nContoh: `/analisis bitcoin`",
        parse_mode="Markdown"
    )

# ==============================
# COMMAND /analisis
# ==============================
async def analisis_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("❌ Format: `/analisis bitcoin` atau `/analisis BBCA.JK`", parse_mode="Markdown")
        return

    aset = context.args[0].lower()
    await update.message.reply_text(f"⏳ Mengambil data {aset}...")

    try:
        # Cek apakah crypto atau saham
        if "." in aset or aset.isupper():
            aset = aset.upper()
            data_harga = get_stock_price(aset)
            berita = get_stock_news(aset)
            indikator = get_stock_indicators(aset)
            jenis = "Saham"
        else:
            data_harga = get_crypto_price(aset)
            berita = get_crypto_news(aset)
            indikator = get_crypto_indicators(aset)
            jenis = "Crypto"

        await update.message.reply_text(f"✅ Data berhasil diambil!\n⏳ AI sedang menganalisis...")

        hasil = analisis_ai(f"Berikan analisis lengkap untuk {aset}", data_harga, berita, indikator)

        # Kirim hasil (maks 4096 karakter per pesan Telegram)
        if len(hasil) > 4000:
            hasil = hasil[:4000] + "..."

        await update.message.reply_text(f"📊 *Analisis {aset}*\n\n{hasil}", parse_mode="Markdown")

    except Exception as e:
        await update.message.reply_text(f"❌ Error: {str(e)}")

# ==============================
# COMMAND /alert
# ==============================
async def alert_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) < 3:
        await update.message.reply_text(
            "❌ Format: `/alert bitcoin naik 70000`\natau `/alert BBCA.JK turun 6000`",
            parse_mode="Markdown"
        )
        return

    nama = context.args[0]
    kondisi = context.args[1].lower()
    harga_target = float(context.args[2])

    if "." in nama or nama.isupper():
        jenis = "saham"
        nama = nama.upper()
    else:
        jenis = "crypto"
        nama = nama.lower()

    tambah_alert(jenis, nama, harga_target, kondisi)
    await update.message.reply_text(
        f"✅ Alert ditambahkan!\n{nama} → {kondisi} Rp/$ {harga_target:,}",
        parse_mode="Markdown"
    )

# ==============================
# COMMAND /alerts
# ==============================
async def alerts_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not alert_list:
        await update.message.reply_text("⚠️ Tidak ada alert aktif!")
        return

    teks = "📋 *Alert Aktif:*\n\n"
    for i, a in enumerate(alert_list, 1):
        teks += f"{i}. {a['nama_aset']} → {a['kondisi']} {a['harga_target']:,}\n"

    await update.message.reply_text(teks, parse_mode="Markdown")

# ==============================
# BUTTON HANDLER
# ==============================
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == "crypto":
        await query.message.reply_text(
            "Ketik: `/analisis bitcoin`\natau `/analisis ethereum`",
            parse_mode="Markdown"
        )
    elif query.data == "saham":
        await query.message.reply_text(
            "Ketik: `/analisis BBCA.JK`\natau `/analisis AAPL`",
            parse_mode="Markdown"
        )
    elif query.data == "alert":
        await query.message.reply_text(
            "Format: `/alert bitcoin naik 70000`\natau `/alert BBCA.JK turun 6000`",
            parse_mode="Markdown"
        )
    elif query.data == "lihat_alert":
        if not alert_list:
            await query.message.reply_text("⚠️ Tidak ada alert aktif!")
        else:
            teks = "📋 *Alert Aktif:*\n\n"
            for i, a in enumerate(alert_list, 1):
                teks += f"{i}. {a['nama_aset']} → {a['kondisi']} {a['harga_target']:,}\n"
            await query.message.reply_text(teks, parse_mode="Markdown")

# ==============================
# JALANKAN BOT
# ==============================
def main():
    app = Application.builder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("analisis", analisis_cmd))
    app.add_handler(CommandHandler("alert", alert_cmd))
    app.add_handler(CommandHandler("alerts", alerts_cmd))
    app.add_handler(CallbackQueryHandler(button_handler))

    print("🤖 Telegram Bot berjalan...")
    app.run_polling()

if __name__ == "__main__":
    main()