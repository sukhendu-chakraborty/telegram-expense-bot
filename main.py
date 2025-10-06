import os
import datetime
import asyncio
from flask import Flask, request
from pymongo import MongoClient
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, ContextTypes, filters

# Load environment variables
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
MONGO_URI = os.getenv("MONGO_URI")

# MongoDB setup
client = MongoClient(MONGO_URI)
db = client["expense_bot"]
expenses_collection = db["expenses"]

# Flask app
app = Flask(__name__)

# Telegram Application
application = Application.builder().token(TOKEN).build()

# --- Helper ---
def format_expenses(records):
    text = "\n".join([f"{r['date']} - {r['item']} - ₹{r['amount']}" for r in records])
    total = sum(r["amount"] for r in records)
    return text, total

# --- Command Handlers ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
   await update.message.reply_text(
    "👋 Hi! I’m your Expense Tracker Bot.\n\n"
    "Send me your expenses like this:\n"
    "`Coffee 50`\n"
    "and I’ll keep a record.\n\n"
    "You can also use these commands to check reports:\n"
    "/today - Today's expenses\n"
    "/week - Last 7 days\n"
    "/month - This month\n"
    "/year - This year",
    parse_mode="Markdown"
)


async def add_expense(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
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

# --- Reports ---
async def today(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    date = datetime.date.today().strftime("%Y-%m-%d")
    records = list(expenses_collection.find({"user_id": user_id, "date": date}))
    if not records:
        await update.message.reply_text("📭 No expenses today.")
        return
    text, total = format_expenses(records)
    await update.message.reply_text(f"📅 *Today's Expenses:*\n{text}\n\n💰 *Total: ₹{total}*", parse_mode="Markdown")

async def week(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    today_date = datetime.date.today()
    start_date = (today_date - datetime.timedelta(days=6)).strftime("%Y-%m-%d")
    end_date = today_date.strftime("%Y-%m-%d")
    records = list(expenses_collection.find({"user_id": user_id, "date": {"$gte": start_date, "$lte": end_date}}))
    if not records:
        await update.message.reply_text("📭 No expenses in the last 7 days.")
        return
    text, total = format_expenses(records)
    await update.message.reply_text(f"📅 *Last 7 Days Expenses:*\n{text}\n\n💰 *Total: ₹{total}*", parse_mode="Markdown")

async def month(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    month_str = datetime.date.today().strftime("%Y-%m")
    records = list(expenses_collection.find({"user_id": user_id, "date": {"$regex": f"^{month_str}"}}))
    if not records:
        await update.message.reply_text("📭 No expenses this month.")
        return
    text, total = format_expenses(records)
    await update.message.reply_text(f"📅 *{datetime.date.today().strftime('%B %Y')} Expenses:*\n{text}\n\n💰 *Total: ₹{total}*", parse_mode="Markdown")

async def year(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    year_str = datetime.date.today().strftime("%Y")
    records = list(expenses_collection.find({"user_id": user_id, "date": {"$regex": f"^{year_str}"}}))
    if not records:
        await update.message.reply_text("📭 No expenses this year.")
        return
    month_totals = {}
    for r in records:
        month = r["date"][:7]
        month_totals[month] = month_totals.get(month, 0) + r["amount"]
    text_lines = [f"{m} - ₹{month_totals[m]}" for m in sorted(month_totals.keys())]
    total = sum(month_totals.values())
    text = "\n".join(text_lines)
    await update.message.reply_text(f"📅 *Yearly Expenses ({year_str}):*\n{text}\n\n💰 *Total: ₹{total}*", parse_mode="Markdown")

# --- Register Handlers ---
application.add_handler(CommandHandler("start", start))
application.add_handler(CommandHandler("today", today))
application.add_handler(CommandHandler("week", week))
application.add_handler(CommandHandler("month", month))
application.add_handler(CommandHandler("year", year))
application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, add_expense))

# --- Flask webhook ---
@app.route(f"/webhook/{TOKEN}", methods=["POST"])
def webhook():
    """Handle Telegram updates from the webhook."""
    try:
        update = Update.de_json(request.get_json(force=True), application.bot)
        asyncio.run(application.initialize())
        asyncio.run(application.process_update(update))
        asyncio.run(application.shutdown())
    except Exception as e:
        print(f"Error in webhook: {e}")
    return "OK", 200




