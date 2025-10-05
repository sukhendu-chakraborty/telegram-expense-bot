import os
import datetime
import time
from dotenv import load_dotenv
from pymongo import MongoClient
from pymongo.errors import ServerSelectionTimeoutError
from flask import Flask, request
from telegram import Bot, Update
from telegram.ext import Dispatcher, CommandHandler, MessageHandler, filters

# ------------------------------
# Load environment variables
# ------------------------------
load_dotenv()
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
MONGO_URI = os.getenv("MONGO_URI")

if not TOKEN or not MONGO_URI:
    raise ValueError("⚠️ Missing TELEGRAM_BOT_TOKEN or MONGO_URI")

# ------------------------------
# Flask app
# ------------------------------
app = Flask(__name__)

# ------------------------------
# MongoDB connection with retry
# ------------------------------
def get_mongo_client(uri, retries=5, delay=3):
    for attempt in range(retries):
        try:
            client = MongoClient(uri, serverSelectionTimeoutMS=5000)
            client.admin.command('ping')
            print("✅ Connected to MongoDB")
            return client
        except ServerSelectionTimeoutError:
            print(f"⚠️ MongoDB connection failed, retrying {attempt + 1}/{retries}...")
            time.sleep(delay)
    raise Exception("❌ Could not connect to MongoDB after multiple attempts")

client = get_mongo_client(MONGO_URI)
db = client["expense_bot"]
expenses_collection = db["expenses"]

# ------------------------------
# Telegram bot setup
# ------------------------------
bot = Bot(token=TOKEN)
dispatcher = Dispatcher(bot, None, workers=0)

# ------------------------------
# Helper function
# ------------------------------
def format_expenses(records):
    text = "\n".join([f"{r['date']} - {r['item']} - ₹{r['amount']}" for r in records])
    total = sum(r["amount"] for r in records)
    return text, total

# ------------------------------
# Command Handlers
# ------------------------------
def start(update, context):
    try:
        update.message.reply_text(
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
    except Exception as e:
        print("❌ Error in /start:", e)

def add_expense(update, context):
    try:
        text = update.message.text
        parts = text.split()
        if len(parts) < 2 or not parts[-1].isdigit():
            update.message.reply_text("⚠️ Format: Item Amount\nExample: Lunch 120")
            return
        item = " ".join(parts[:-1])
        amount = int(parts[-1])
        date = datetime.date.today().strftime("%Y-%m-%d")
        user_id = update.message.from_user.id
        try:
            expenses_collection.insert_one({
                "user_id": user_id,
                "date": date,
                "item": item,
                "amount": amount
            })
        except Exception as e:
            print("❌ MongoDB insert failed:", e)
            update.message.reply_text("⚠️ Could not save your expense, try again.")
            return
        update.message.reply_text(f"✅ Recorded: {item} - ₹{amount}")
    except Exception as e:
        print("❌ Error in add_expense:", e)

def today(update, context):
    try:
        user_id = update.message.from_user.id
        date = datetime.date.today().strftime("%Y-%m-%d")
        records = list(expenses_collection.find({"user_id": user_id, "date": date}))
        if not records:
            update.message.reply_text("📭 No expenses today.")
            return
        text, total = format_expenses(records)
        update.message.reply_text(f"📅 *Today's Expenses:*\n{text}\n\n💰 *Total: ₹{total}*", parse_mode="Markdown")
    except Exception as e:
        print("❌ Error in /today:", e)

def week(update, context):
    try:
        user_id = update.message.from_user.id
        today_date = datetime.date.today()
        start_date = (today_date - datetime.timedelta(days=6)).strftime("%Y-%m-%d")
        end_date = today_date.strftime("%Y-%m-%d")
        records = list(expenses_collection.find({
            "user_id": user_id,
            "date": {"$gte": start_date, "$lte": end_date}
        }))
        if not records:
            update.message.reply_text("📭 No expenses in the last 7 days.")
            return
        text, total = format_expenses(records)
        update.message.reply_text(f"📅 *Last 7 Days Expenses:*\n{text}\n\n💰 *Total: ₹{total}*", parse_mode="Markdown")
    except Exception as e:
        print("❌ Error in /week:", e)

def month(update, context):
    try:
        user_id = update.message.from_user.id
        today_date = datetime.date.today()
        month_str = today_date.strftime("%Y-%m")
        records = list(expenses_collection.find({
            "user_id": user_id,
            "date": {"$regex": f"^{month_str}"}
        }))
        if not records:
            update.message.reply_text("📭 No expenses this month.")
            return
        text, total = format_expenses(records)
        update.message.reply_text(f"📅 *{today_date.strftime('%B %Y')} Expenses:*\n{text}\n\n💰 *Total: ₹{total}*", parse_mode="Markdown")
    except Exception as e:
        print("❌ Error in /month:", e)

def year(update, context):
    try:
        user_id = update.message.from_user.id
        today_date = datetime.date.today()
        year_str = today_date.strftime("%Y")
        records = list(expenses_collection.find({
            "user_id": user_id,
            "date": {"$regex": f"^{year_str}"}
        }))
        if not records:
            update.message.reply_text("📭 No expenses this year.")
            return
        # Group by month
        month_totals = {}
        for r in records:
            month = r["date"][:7]
            month_totals[month] = month_totals.get(month, 0) + r["amount"]
        text_lines = [f"{m} - ₹{month_totals[m]}" for m in sorted(month_totals.keys())]
        total = sum(month_totals.values())
        text = "\n".join(text_lines)
        update.message.reply_text(f"📅 *Yearly Expenses ({year_str}):*\n{text}\n\n💰 *Total: ₹{total}*", parse_mode="Markdown")
    except Exception as e:
        print("❌ Error in /year:", e)

# ------------------------------
# Register all handlers
# ------------------------------
dispatcher.add_handler(CommandHandler("start", start))
dispatcher.add_handler(CommandHandler("today", today))
dispatcher.add_handler(CommandHandler("week", week))
dispatcher.add_handler(CommandHandler("month", month))
dispatcher.add_handler(CommandHandler("year", year))
dispatcher.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, add_expense))

# ------------------------------
# Flask webhook route
# ------------------------------
@app.route(f"/webhook/{TOKEN}", methods=["POST"])
def webhook():
    try:
        update = Update.de_json(request.get_json(force=True), bot)
        dispatcher.process_update(update)
        return "ok"
    except Exception as e:
        print("❌ Error in webhook:", e)
        return "error"

# ------------------------------
# Local testing
# ------------------------------
if __name__ == "__main__":
    app.run(port=5000)
