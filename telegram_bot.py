from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes
from dotenv import load_dotenv
import os
import sys
import time
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from main import (
    get_crypto_price, get_stock_price, 
    get_crypto_news, get_stock_news, 
    get_crypto_indicators, get_stock_indicators, 
    analisis_ai_v2, analisis_ai,
    alert_list, tambah_alert, simpan_alert,
    simpan_ke_sheets, simpan_ke_excel, catat_sinyal,
    hitung_performa, update_sinyal_closed,
    DEFAULT_MODAL
)

load_dotenv()
TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

# Per-user modal storage
user_modals = {}

def get_user_modal(user_id):
    """Ambil modal user, default Rp 1.000.000"""
    return user_modals.get(user_id, DEFAULT_MODAL)

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
    keyboard = [
        [InlineKeyboardButton("📈 Analisis Crypto", callback_data="crypto")],
        [InlineKeyboardButton("📉 Analisis Saham", callback_data="saham")],
        [InlineKeyboardButton("🔔 Set Alert", callback_data="alert")],
        [InlineKeyboardButton("📋 Lihat Alert Aktif", callback_data="lihat_alert")],
        [InlineKeyboardButton("📊 Performa Bot", callback_data="performa")],
        [InlineKeyboardButton("💰 Set Modal", callback_data="set_modal")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        "🤖 *CRYPTO & SAHAM AGENT v2.0*\n"
        "10-Point Analysis System\n\n"
        "Pilih menu di bawah:",
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

    aset = context.args[0].strip()
    user_id = update.effective_user.id
    modal = get_user_modal(user_id)
    
    await update.message.reply_text(
        f"⏳ Mengambil data *{aset}*...\n"
        f"💰 Modal: Rp {modal:,.0f}",
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

        # Kirim hasil analisis
        await kirim_pesan_panjang(update, hasil)

        # Simpan ke Google Sheets (setelah pesan terkirim)
        try:
            simpan_ke_sheets(jenis, aset, data_harga, hasil, indikator)

            # Catat sinyal ke Performance sheet
            if analysis_data.get("sinyal") != "HOLD":
                catat_sinyal(
                    jenis, aset,
                    analysis_data["entry"],
                    analysis_data["sinyal"],
                    analysis_data["sl"],
                    analysis_data["tp"],
                    analysis_data.get("skor_detail")
                )
        except Exception as e:
            print(f"⚠️ Gagal simpan/catat performa: {e}")

    except Exception as e:
        print(f"❌ ERROR analisis {aset}: {type(e).__name__}: {e}")
        try:
            await update.message.reply_text(
                f"⚠️ Terjadi error saat menganalisis {aset}\n\nDetail: {type(e).__name__}\nCoba beberapa saat lagi!"
            )
        except:
            await update.message.reply_text(f"⚠️ Error: {e}")

# ==============================
# COMMAND /modal
# ==============================
async def modal_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    if not context.args:
        current = get_user_modal(user_id)
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
        
        user_modals[user_id] = modal_baru
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
    teks = """
🤖 *PANDUAN CRYPTO & SAHAM AGENT v2.0*
_(10-Point Analysis System)_

📌 *Perintah yang tersedia:*

`/start` → Menu utama
`/analisis [aset]` → Analisis harga & sinyal (10-Point)
`/modal [jumlah]` → Set modal trading
`/alert [aset] [kondisi] [harga]` → Set alert harga
`/alerts` → Lihat semua alert aktif
`/performa [aset]` → Lihat & update performa
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
            "📈 *Analisis Crypto (10-Point System)*\n\nKetik perintah:\n`/analisis bitcoin`\n`/analisis ethereum`\n`/analisis solana`",
            parse_mode="Markdown"
        )
    elif query.data == "saham":
        await query.message.reply_text(
            "📉 *Analisis Saham (10-Point System)*\n\nKetik perintah:\n`/analisis BBCA.JK`\n`/analisis BBRI.JK`\n`/analisis AAPL`",
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
        await query.message.reply_text("⏳ Menghitung performa bot...")
        performa = hitung_performa()
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
        current = get_user_modal(user_id)
        await query.message.reply_text(
            f"💰 *Modal kamu saat ini:* Rp {current:,.0f}\n\n"
            f"Untuk mengubah, ketik:\n`/modal [jumlah]`\n\n"
            f"Contoh: `/modal 5000000`",
            parse_mode="Markdown"
        )

# ==============================
# COMMAND /performa
# ==============================
async def performa_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("⏳ Menghitung performa bot...")
    
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
    app.add_handler(CommandHandler("modal", modal_cmd))
    app.add_handler(CommandHandler("alert", alert_cmd))
    app.add_handler(CommandHandler("alerts", alerts_cmd))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("performa", performa_cmd))
    app.add_handler(CallbackQueryHandler(button_handler))

    print("🤖 Telegram Bot v2.0 (10-Point System) berjalan...")
    app.run_polling()

if __name__ == "__main__":
    main()