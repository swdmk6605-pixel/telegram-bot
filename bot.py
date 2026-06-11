import os
import sqlite3
import asyncio
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    ContextTypes, MessageHandler, filters
)

BOT_TOKEN = os.getenv("BOT_TOKEN", "YOUR_BOT_TOKEN")
CHANNEL_ID = int(os.getenv("CHANNEL_ID", "-1003990153810"))
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))

def init_db():
    conn = sqlite3.connect("subscriptions.db")
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS subscriptions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            username TEXT,
            full_name TEXT,
            invite_link TEXT,
            plan TEXT,
            start_date TEXT,
            end_date TEXT,
            status TEXT DEFAULT 'active',
            notified_3days INTEGER DEFAULT 0,
            notified_1day INTEGER DEFAULT 0
        )
    """)
    conn.commit()
    conn.close()

def get_db():
    return sqlite3.connect("subscriptions.db")

def is_admin(user_id):
    return user_id == ADMIN_ID

def get_plan_days(plan):
    plans = {"daily": 1, "weekly": 7, "monthly": 30, "yearly": 365}
    return plans.get(plan, 30)

def get_plan_name(plan):
    names = {"daily": "يومي", "weekly": "أسبوعي", "monthly": "شهري", "yearly": "سنوي"}
    return names.get(plan, plan)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if is_admin(user.id):
        keyboard = [
            [InlineKeyboardButton("➕ إضافة مشترك", callback_data="add_member")],
            [InlineKeyboardButton("📋 قائمة المشتركين", callback_data="list_members")],
            [InlineKeyboardButton("📊 إحصائيات", callback_data="stats")],
        ]
        await update.message.reply_text(
            "🎛️ لوحة تحكم الاشتراكات\n\nاختر ما تريد:",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="Markdown"
        )
    else:
        conn = get_db()
        c = conn.cursor()
        c.execute("SELECT * FROM subscriptions WHERE user_id=? AND status='active'", (user.id,))
        sub = c.fetchone()
        conn.close()
        if sub:
            end_date = datetime.strptime(sub[7], "%Y-%m-%d")
            remaining = (end_date - datetime.now()).days
            await update.message.reply_text(
                f"✅ اشتراكك فعال\n📋 الخطة: {get_plan_name(sub[5])}\n📅 ينتهي: {sub[7]}\n⏳ المتبقي: {remaining} يوم"
            )
        else:
            await update.message.reply_text("❌ ليس لديك اشتراك فعال. تواصل مع الأدمن.")

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    if not is_admin(query.from_user.id):
        await query.edit_message_text("❌ ليس لديك صلاحية!")
        return

    if data == "add_member":
        context.user_data["adding_member"] = True
        await query.edit_message_text("➕ أرسل ID المشترك أو يوزرنيمه:")

    elif data == "list_members":
        conn = get_db()
        c = conn.cursor()
        c.execute("SELECT * FROM subscriptions WHERE status='active' ORDER BY end_date ASC")
        members = c.fetchall()
        conn.close()
        if not members:
            await query.edit_message_text("📋 لا يوجد مشتركين فعالين.")
            return
        text = "📋 المشتركون الفعالون:\n\n"
        for i, sub in enumerate(members[:20], 1):
            end_date = datetime.strptime(sub[7], "%Y-%m-%d")
            remaining = (end_date - datetime.now()).days
            emoji = "🟢" if remaining > 7 else "🟡" if remaining > 3 else "🔴"
            text += f"{i}. {emoji} {sub[3]} | {get_plan_name(sub[5])} | {remaining} يوم\n"
        keyboard = [[InlineKeyboardButton("🔙 رجوع", callback_data="back_main")]]
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))

    elif data == "stats":
        conn = get_db()
        c = conn.cursor()
        c.execute("SELECT COUNT(*) FROM subscriptions WHERE status='active'")
        active = c.fetchone()[0]
        c.execute("SELECT COUNT(*) FROM subscriptions WHERE status='expired'")
        expired = c.fetchone()[0]
        conn.close()
        keyboard = [[InlineKeyboardButton("🔙 رجوع", callback_data="back_main")]]
        await query.edit_message_text(
            f"📊 الإحصائيات\n\n✅ فعالين: {active}\n❌ منتهية: {expired}",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

    elif data == "back_main":
        keyboard = [
            [InlineKeyboardButton("➕ إضافة مشترك", callback_data="add_member")],
            [InlineKeyboardButton("📋 قائمة المشتركين", callback_data="list_members")],
            [InlineKeyboardButton("📊 إحصائيات", callback_data="stats")],
        ]
        await query.edit_message_text("🎛️ لوحة تحكم الاشتراكات\n\nاختر ما تريد:",
                                       reply_markup=InlineKeyboardMarkup(keyboard))

    elif data.startswith("plan_"):
        plan = data.replace("plan_", "")
        member_id = context.user_data.get("new_member_id", "")
        if not member_id:
            await query.edit_message_text("❌ حدث خطأ، حاول مرة أخرى!")
            return
        try:
            days = get_plan_days(plan)
            expire_date = datetime.now() + timedelta(days=days)
            invite = await context.bot.create_chat_invite_link(
                chat_id=CHANNEL_ID, member_limit=1, expire_date=expire_date
            )
            if member_id.startswith("@"):
                chat = await context.bot.get_chat(member_id)
                user_id = chat.id
                full_name = chat.first_name or member_id
            else:
                user_id = int(member_id)
                try:
                    chat = await context.bot.get_chat(user_id)
                    full_name = chat.first_name or str(user_id)
                except:
                    full_name = str(user_id)

            start_date = datetime.now().strftime("%Y-%m-%d")
            end_date = (datetime.now() + timedelta(days=days)).strftime("%Y-%m-%d")
            conn = get_db()
            c = conn.cursor()
            c.execute("""INSERT INTO subscriptions (user_id, username, full_name, invite_link, plan, start_date, end_date, status)
                         VALUES (?, ?, ?, ?, ?, ?, ?, 'active')""",
                      (user_id, "", full_name, invite.invite_link, plan, start_date, end_date))
            conn.commit()
            conn.close()

            await query.edit_message_text(
                f"✅ تم إنشاء الاشتراك!\n\n👤 {full_name}\n📋 {get_plan_name(plan)}\n📅 ينتهي: {end_date}\n\n🔗 رابط الدعوة:\n{invite.invite_link}"
            )
            try:
                await context.bot.send_message(
                    chat_id=user_id,
                    text=f"🎉 تم تفعيل اشتراكك!\n📋 {get_plan_name(plan)}\n📅 ينتهي: {end_date}\n\n🔗 رابط الدخول:\n{invite.invite_link}"
                )
            except:
                pass
            context.user_data.clear()
        except Exception as e:
            await query.edit_message_text(f"❌ خطأ: {str(e)}")

    elif data.startswith("delete_"):
        sub_id = data.replace("delete_", "")
        conn = get_db()
        c = conn.cursor()
        c.execute("SELECT * FROM subscriptions WHERE id=?", (sub_id,))
        sub = c.fetchone()
        if sub:
            c.execute("UPDATE subscriptions SET status='expired' WHERE id=?", (sub_id,))
            conn.commit()
            if sub[1]:
                try:
                    await context.bot.ban_chat_member(CHANNEL_ID, sub[1])
                    await asyncio.sleep(1)
                    await context.bot.unban_chat_member(CHANNEL_ID, sub[1])
                    await context.bot.send_message(chat_id=sub[1], text="❌ تم إلغاء اشتراكك.")
                except:
                    pass
        conn.close()
        await query.edit_message_text("✅ تم حذف الاشتراك وطرد المشترك!")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not is_admin(user.id):
        return
    text = update.message.text.strip()

    if context.user_data.get("adding_member"):
        context.user_data["new_member_id"] = text
        context.user_data["adding_member"] = False
        keyboard = [
            [InlineKeyboardButton("📅 يومي", callback_data="plan_daily")],
            [InlineKeyboardButton("📆 أسبوعي", callback_data="plan_weekly")],
            [InlineKeyboardButton("🗓️ شهري", callback_data="plan_monthly")],
            [InlineKeyboardButton("🎯 سنوي", callback_data="plan_yearly")]
        ]
        await update.message.reply_text(f"✅ المعرف: {text}\n\nاختر نوع الاشتراك:",
                                         reply_markup=InlineKeyboardMarkup(keyboard))

async def check_subscriptions(context: ContextTypes.DEFAULT_TYPE):
    conn = get_db()
    c = conn.cursor()
    c.execute("""SELECT * FROM subscriptions WHERE status='active'
                 AND date(end_date) <= date('now', '+3 days')
                 AND date(end_date) > date('now') AND notified_3days=0""")
    for sub in c.fetchall():
        remaining = (datetime.strptime(sub[7], "%Y-%m-%d") - datetime.now()).days + 1
        if sub[1]:
            try:
                await context.bot.send_message(chat_id=sub[1],
                    text=f"⚠️ اشتراكك ينتهي خلال {remaining} يوم! تاريخ الانتهاء: {sub[7]}")
            except:
                pass
        try:
            await context.bot.send_message(chat_id=ADMIN_ID,
                text=f"⚠️ اشتراك {sub[3]} ينتهي خلال {remaining} يوم")
        except:
            pass
        c.execute("UPDATE subscriptions SET notified_3days=1 WHERE id=?", (sub[0],))

    c.execute("""SELECT * FROM subscriptions WHERE status='active'
                 AND date(end_date) < date('now')""")
    for sub in c.fetchall():
        if sub[1]:
            try:
                await context.bot.ban_chat_member(CHANNEL_ID, sub[1])
                await asyncio.sleep(1)
                await context.bot.unban_chat_member(CHANNEL_ID, sub[1])
                await context.bot.send_message(chat_id=sub[1],
                    text="❌ انتهى اشتراكك وتم طردك. تواصل مع الأدمن للتجديد.")
            except:
                pass
            try:
                await context.bot.send_message(chat_id=ADMIN_ID,
                    text=f"🚫 تم طرد {sub[3]} لانتهاء اشتراكه")
            except:
                pass
        c.execute("UPDATE subscriptions SET status='expired' WHERE id=?", (sub[0],))

    conn.commit()
    conn.close()

def main():
    init_db()
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    print("✅ البوت يعمل...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
    
