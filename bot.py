import logging
import requests
import sqlite3
from datetime import date
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes

# مفاتيح الربط
TELEGRAM_TOKEN = "9084080147:AAEaPg6HH_GHH84odazOSocga6C1BvrXvIc"
YOUTUBE_API_KEY = "AIzaSyBlvopfdKMk0ZhVFfvwH5r5xGtEri89DtQ"

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
DB_NAME = "users.db"


# ---------------------------------------------------------
# 1. إدارة قاعدة البيانات والحدود اليومية
# ---------------------------------------------------------
def init_db():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            last_search_date TEXT,
            daily_count INTEGER DEFAULT 0
        )
    ''')
    conn.commit()
    conn.close()


def check_and_update_limit(user_id: int, max_limit: int = 3) -> tuple[bool, int]:
    today_str = str(date.today())
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()

    cursor.execute("SELECT last_search_date, daily_count FROM users WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()

    if row is None:
        cursor.execute("INSERT INTO users (user_id, last_search_date, daily_count) VALUES (?, ?, ?)",
                       (user_id, today_str, 1))
        conn.commit()
        conn.close()
        return True, 1

    last_date, count = row
    if last_date != today_str:
        cursor.execute("UPDATE users SET last_search_date = ?, daily_count = 1 WHERE user_id = ?",
                       (today_str, user_id))
        conn.commit()
        conn.close()
        return True, 1
    else:
        if count < max_limit:
            new_count = count + 1
            cursor.execute("UPDATE users SET daily_count = ? WHERE user_id = ?", (new_count, user_id))
            conn.commit()
            conn.close()
            return True, new_count
        else:
            conn.close()
            return False, count


# ---------------------------------------------------------
# 2. دالة سحب بيانات يوتيوب API
# ---------------------------------------------------------
def get_youtube_stats(channel_query):
    clean_query = channel_query.replace("@", "").strip()
    url = f"https://www.googleapis.com/youtube/v3/channels?part=statistics,snippet&forHandle={clean_query}&key={YOUTUBE_API_KEY}"
    res = requests.get(url).json()

    if "items" not in res or not res["items"]:
        search_url = f"https://www.googleapis.com/youtube/v3/search?part=snippet&type=channel&q={clean_query}&key={YOUTUBE_API_KEY}"
        search_res = requests.get(search_url).json()
        if search_res.get("items"):
            channel_id = search_res["items"][0]["snippet"]["channelId"]
            url = f"https://www.googleapis.com/youtube/v3/channels?part=statistics,snippet&id={channel_id}&key={YOUTUBE_API_KEY}"
            res = requests.get(url).json()

    if res.get("items"):
        item = res["items"][0]
        snippet = item["snippet"]
        stats = item["statistics"]
        return {
            "title": snippet.get("title", "غير محدد"),
            "subscribers": int(stats.get("subscriberCount", 0)),
            "views": int(stats.get("viewCount", 0)),
            "videos": int(stats.get("videoCount", 0))
        }
    return None


# ---------------------------------------------------------
# 3. معالجة الأوامر والتفاعل
# ---------------------------------------------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("▶️ فحص قناة يوتيوب", callback_data='check_youtube')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    welcome_text = (
        "أهلاً بك في **بوت الرادار 🔍**\n\n"
        "لديك **3 فحوصات مجانية يومياً**.\n"
        "أرسل اسم القناة أو يوزر القناة لفحصها (مثال: `@MrBeast`):"
    )
    await update.message.reply_text(welcome_text, reply_markup=reply_markup, parse_mode='Markdown')


async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.data == 'check_youtube':
        await query.edit_message_text("أرسل اسم أو يوزر قناة اليوتيوب الآن:")


async def process_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_input = update.message.text

    can_search, used_count = check_and_update_limit(user_id, max_limit=3)

    if not can_search:
        limit_msg = (
            "⚠️ **استنفدت رصيدك المجاني لهذا اليوم (3/3)!**\n\n"
            "يرجى الانتظار حتى الغد لتجديد الرصيد تلقائياً."
        )
        await update.message.reply_text(limit_msg, parse_mode='Markdown')
        return

    await update.message.reply_text(f"⏳ جاري فحص البيانات... (استهلاك {used_count} من 3)")

    data = get_youtube_stats(user_input)

    if data:
        avg_views = data["views"] // data["videos"] if data["videos"] > 0 else 0
        report = (
            f"📊 **تقرير قناة يوتيوب الحقيقي** ▶️\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"اسم القناة: **{data['title']}**\n"
            f"👥 المشتركين: **{data['subscribers']:,}**\n"
            f"👁️ إجمالي المشاهدات: **{data['views']:,}**\n"
            f"🎬 عدد الفيديوهات: **{data['videos']:,}**\n"
            f"📈 متوسط المشاهدات: **{avg_views:,}**\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"متبقي لك اليوم: **{3 - used_count} محاولات**"
        )
        await update.message.reply_text(report, parse_mode='Markdown')
    else:
        await update.message.reply_text("❌ لم يتم العثور على القناة، تأكد من كتابة المعرف أو الاسم بشكل صحيح.")


if __name__ == '__main__':
    init_db()
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, process_message))

    print("البوت يعمل بالبيانات الحية ونظام الحدود...")
    app.run_polling()