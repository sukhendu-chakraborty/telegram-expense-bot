import os
import datetime
from flask import Flask, request
from pymongo import MongoClient
from telegram import Update, Bot
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes
import asyncio

# ---------------- Environment Variables ----------------
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
MONGO_URI = os.getenv("MONGO_URI")

if not TOKEN or not MONGO_URI:
    raise ValueError("Missing TELEGRAM_BOT_TOKEN or MONGO_URI in environment variables")

# ---------------- MongoDB Setup ----------------
client = MongoClient(MONGO_URI)
db = client["expense_bot"]
expenses_collection = db["expenses"]

# ---------------- Telegram Bot Application ----------------
bot_app = ApplicationBuilder().token(TOKEN).build()
bot_instance = Bot(TOKEN)

# ---------------- Handlers ----------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Hi! I’m your Expense Tracker Bot.\n\n"
        "Send me your expenses like this:\n"
        "`Coffee 50`\n"
        "and I’ll keep a record.\n\n"
        "Commands:\n"
        "/today - Today's expenses\n"
        "/week - Last 7 days\n"
        "/month - Current month\n"
        "/year - Current year\n",
        parse_mode="Markdown"
    )

async def add_expense(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    parts = text.split()
    
    if len(parts) < 2 or not parts[-1].isdigit():
        await update.message.reply_text("⚠️ Format: Item Amount\nExample: Lunch 120")
        return

    item = " ".join(parts[:-1])
    amount = int(parts[-1])
    date = datetime.date.today().strftime("%Y-%m-%d")
    user_id = update.message.from_user.id

    expenses_collection.insert_one({
        "user_id": user_id,
        "date": date,
        "item": item,
        "amount": amount
    })

    await update.message.reply_text(f"✅ Recorded: {item} - ₹{amount}")

# Helper to format expenses
def format_expenses(records):
    text = "\n".join([f"{r['date']} - {r['item']} - ₹{r['amount']}" for r in records])
    total = sum(r["amount"] for r in records)
    return text, total

async def today(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    date = datetime.date.today().strftime("%Y-%m-%d")
    records = list(expenses_collection.find({"user_id": user_id, "date": date}))

    if not records:
        await update.message.reply_text("📭 No expenses today.")
        return

    text, total = format_expenses(records)
    await update.message.reply_text(f"📅 *Today's Expenses:*\n{text}\n\n💰 *Total: ₹{total}*", parse_mode="Markdown")

async def week(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    today_date = datetime.date.today()
    start_date = (today_date - datetime.timedelta(days=6)).strftime("%Y-%m-%d")
    end_date = today_date.strftime("%Y-%m-%d")
    records = list(expenses_collection.find({
        "user_id": user_id,
        "date": {"$gte": start_date, "$lte": end_date}
    }))

    if not records:
        await update.message.reply_text("📭 No expenses in the last 7 days.")
        return

    text, total = format_expenses(records)
    await update.message.reply_text(f"📅 *Last 7 Days Expenses:*\n{text}\n\n💰 *Total: ₹{total}*", parse_mode="Markdown")

async def month(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    month_str = datetime.date.today().strftime("%Y-%m")
    records = list(expenses_collection.find({
        "user_id": user_id,
        "date": {"$regex": f"^{month_str}"}
    }))

    if not records:
        await update.message.reply_text("📭 No expenses this month.")
        return

    text, total = format_expenses(records)
    await update.message.reply_text(f"📅 *{datetime.date.today().strftime('%B %Y')} Expenses:*\n{text}\n\n💰 *Total: ₹{total}*", parse_mode="Markdown")

async def year(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    year_str = datetime.date.today().strftime("%Y")
    records = list(expenses_collection.find({
        "user_id": user_id,
        "date": {"$regex": f"^{year_str}"}
    }))

    if not records:
        await update.message.reply_text("📭 No expenses this year.")
        return

    month_totals = {}
    for r in records:
        month = r["date"][:7]  # YYYY-MM
        month_totals[month] = month_totals.get(month, 0) + r["amount"]

    text_lines = [f"{m} - ₹{month_totals[m]}" for m in sorted(month_totals.keys())]
    total = sum(month_totals.values())
    text = "\n".join(text_lines)
    await update.message.reply_text(f"📅 *Yearly Expenses ({year_str}):*\n{text}\n\n💰 *Total: ₹{total}*", parse_mode="Markdown")

# ---------------- Register Handlers ----------------
bot_app.add_handler(CommandHandler("start", start))
bot_app.add_handler(CommandHandler("today", today))
bot_app.add_handler(CommandHandler("week", week))
bot_app.add_handler(CommandHandler("month", month))
bot_app.add_handler(CommandHandler("year", year))
bot_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, add_expense))

# ---------------- Flask Webhook Server ----------------
flask_app = Flask(__name__)

@flask_app.route("/")
def index():
    return "Expense Bot is running!"

@flask_app.route(f"/webhook/{TOKEN}", methods=["POST"])
def webhook():
    update = Update.de_json(request.get_json(force=True), bot_instance)
    asyncio.run(bot_app.update_queue.put(update))
    return "OK"

# ---------------- Run ----------------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    flask_app.run(host="0.0.0.0", port=port)
