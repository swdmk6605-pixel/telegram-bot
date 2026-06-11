import os
import sqlite3
import asyncio
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ChatPermissions
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    ContextTypes, MessageHandler, filters
)

# ==================== الإعدادات ====================
BOT_TOKEN = os.getenv("BOT_TOKEN", "YOUR_BOT_TOKEN")
CHANNEL_ID = int(os.getenv("CHANNEL_ID", "-1003990153810"))
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))  # ضع ID حسابك هنا

# ==================== قاعدة البيانات ====================
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

# ==================== دوال مساعدة ====================
def is_admin(user_id):
    return user_id == ADMIN_ID

def get_plan_days(plan):
    plans = {
        "daily": 1,
        "weekly": 7,
        "monthly": 30,
        "yearly": 365
    }
    return plans.get(plan, 30)

def get_plan_name(plan):
    names = {
        "daily": "يومي 📅",
        "weekly": "أسبوعي 📆",
        "monthly": "شهري 🗓️",
        "yearly": "سنوي 🎯"
    }
    return names.get(plan, plan)

# ==================== الأوامر ====================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    
    if is_admin(user.id):
        keyboard = [
            [InlineKeyboardButton("➕ إضافة مشترك جديد", callback_data="add_member")],
            [InlineKeyboardButton("📋 قائمة المشتركين", callback_data="list_members")],
            [InlineKeyboardButton("📊 إحصائيات", callback_data="stats")],
            [InlineKeyboardButton("🔍 بحث عن مشترك", callback_data="search_member")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(
            f"👋 أهلاً {user.first_name}!\n\n"
            "🎛️ **لوحة تحكم الاشتراكات**\n\n"
            "اختر ما تريد:",
            reply_markup=reply_markup,
            parse_mode="Markdown"
        )
    else:
        # للمشترك العادي
        conn = get_db()
        c = conn.cursor()
        c.execute("SELECT * FROM subscriptions WHERE user_id=? AND status='active'", (user.id,))
        sub = c.fetchone()
        conn.close()
        
        if sub:
            end_date = datetime.strptime(sub[7], "%Y-%m-%d")
            remaining = (end_date - datetime.now()).days
            await update.message.reply_text(
                f"👋 أهلاً {user.first_name}!\n\n"
                f"✅ اشتراكك **فعال**\n"
                f"📋 الخطة: {get_plan_name(sub[5])}\n"
                f"📅 ينتهي في: {sub[7]}\n"
                f"⏳ المتبقي: {remaining} يوم",
                parse_mode="Markdown"
            )
        else:
            await update.message.reply_text(
                f"👋 أهلاً {user.first_name}!\n\n"
                "❌ ليس لديك اشتراك فعال حالياً.\n"
                "تواصل مع الأدمن للاشتراك."
            )

async def add_member_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if not is_admin(query.from_user.id):
        await query.edit_message_text("❌ ليس لديك صلاحية!")
        return
    
    context.user_data["adding_member"] = True
    await query.edit_message_text(
        "➕ **إضافة مشترك جديد**\n\n"
        "أرسل **ID المستخدم** أو **يوزرنيمه**\n\n"
        "مثال:\n"
        "`123456789`\n"
        "أو\n"
        "`@username`",
        parse_mode="Markdown"
    )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    
    if not is_admin(user.id):
        return
    
    if context.user_data.get("adding_member"):
        text = update.message.text.strip()
        
        # حفظ المعرف مؤقتاً
        context.user_data["new_member_id"] = text
        context.user_data["adding_member"] = False
        context.user_data["choosing_plan"] = True
        
        keyboard = [
            [InlineKeyboardButton("📅 يومي", callback_data="plan_daily")],
            [InlineKeyboardButton("📆 أسبوعي", callback_data="plan_weekly")],
            [InlineKeyboardButton("🗓️ شهري", callback_data="plan_monthly")],
            [InlineKeyboardButton("🎯 سنوي", callback_data="plan_yearly")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(
            f"✅ تم حفظ المعرف: `{text}`\n\n"
            "اختر نوع الاشتراك:",
            reply_markup=reply_markup,
            parse_mode="Markdown"
        )
    
    elif context.user_data.get("searching"):
        text = update.message.text.strip()
        context.user_data["searching"] = False
        
        conn = get_db()
        c = conn.cursor()
        c.execute(
            "SELECT * FROM subscriptions WHERE user_id=? OR username LIKE ?",
            (text, f"%{text}%")
        )
        results = c.fetchall()
        conn.close()
        
        if not results:
            await update.message.reply_text("❌ لم يتم العثور على مشترك!")
            return
        
        for sub in results:
            status_emoji = "✅" if sub[8] == "active" else "❌"
            keyboard = [
                [InlineKeyboardButton("🗑️ حذف الاشتراك", callback_data=f"delete_{sub[0]}")],
                [InlineKeyboardButton("🔄 تجديد الاشتراك", callback_data=f"renew_{sub[0]}")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await update.message.reply_text(
                f"{status_emoji} **معلومات المشترك**\n\n"
                f"👤 الاسم: {sub[3]}\n"
                f"🆔 ID: `{sub[1]}`\n"
                f"📋 الخطة: {get_plan_name(sub[5])}\n"
                f"📅 بداية: {sub[6]}\n"
                f"📅 نهاية: {sub[7]}\n"
                f"📊 الحالة: {sub[8]}",
                reply_markup=reply_markup,
                parse_mode="Markdown"
            )

async def choose_plan(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if not is_admin(query.from_user.id):
        return
    
    plan = query.data.replace("plan_", "")
    member_id = context.user_data.get("new_member_id", "")
    
    if not member_id:
        await query.edit_message_text("❌ حدث خطأ، حاول مرة أخرى!")
        return
    
    # إنشاء رابط دعوة خاص
    try:
        days = get_plan_days(plan)
        expire_date = datetime.now() + timedelta(days=days)
        
        # إنشاء رابط دعوة
        invite = await context.bot.create_chat_invite_link(
            chat_id=CHANNEL_ID,
            member_limit=1,
            expire_date=expire_date
        )
        
        # تحديد user_id
        if member_id.startswith("@"):
            try:
                chat = await context.bot.get_chat(member_id)
                user_id = chat.id
                username = chat.username or ""
                full_name = chat.first_name or member_id
            except:
                user_id = 0
                username = member_id
                full_name = member_id
        else:
            try:
                user_id = int(member_id)
                try:
                    chat = await context.bot.get_chat(user_id)
                    username = chat.username or ""
                    full_name = chat.first_name or str(user_id)
                except:
                    username = ""
                    full_name = str(user_id)
            except:
                user_id = 0
                username = member_id
                full_name = member_id
        
        # حفظ في قاعدة البيانات
        start_date = datetime.now().strftime("%Y-%m-%d")
        end_date = (datetime.now() + timedelta(days=get_plan_days(plan))).strftime("%Y-%m-%d")
        
        conn = get_db()
        c = conn.cursor()
        c.execute("""
            INSERT INTO subscriptions (user_id, username, full_name, invite_link, plan, start_date, end_date, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, 'active')
        """, (user_id, username, full_name, invite.invite_link, plan, start_date, end_date))
        conn.commit()
        conn.close()
        
        # إرسال الرابط للأدمن
        await query.edit_message_text(
            f"✅ **تم إنشاء الاشتراك بنجاح!**\n\n"
            f"👤 المشترك: {full_name}\n"
            f"🆔 ID: `{user_id}`\n"
            f"📋 الخطة: {get_plan_name(plan)}\n"
            f"📅 ينتهي في: {end_date}\n\n"
            f"🔗 **رابط الدعوة الخاص:**\n"
            f"`{invite.invite_link}`\n\n"
            "أرسل هذا الرابط للمشترك 👆",
            parse_mode="Markdown"
        )
        
        # إرسال الرابط للمشترك إذا عندنا ID صحيح
        if user_id and user_id != 0:
            try:
                await context.bot.send_message(
                    chat_id=user_id,
                    text=f"🎉 **تم تفعيل اشتراكك!**\n\n"
                         f"📋 الخطة: {get_plan_name(plan)}\n"
                         f"📅 ينتهي في: {end_date}\n\n"
                         f"🔗 **رابط دخول القناة:**\n"
                         f"{invite.invite_link}\n\n"
                         "اضغط على الرابط للانضمام للقناة 👆",
                    parse_mode="Markdown"
                )
            except:
                pass
        
        context.user_data.clear()
        
    except Exception as e:
        await query.edit_message_text(f"❌ حدث خطأ: {str(e)}")

async def list_members(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if not is_admin(query.from_user.id):
        return
    
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT * FROM subscriptions WHERE status='active' ORDER BY end_date ASC")
    members = c.fetchall()
    conn.close()
    
    if not members:
        await query.edit_message_text("📋 لا يوجد مشتركين فعالين حالياً!")
        return
    
    text = "📋 **قائمة المشتركين الفعالين:**\n\n"
    for i, sub in enumerate(members[:20], 1):  # أول 20 مشترك
        end_date = datetime.strptime(sub[7], "%Y-%m-%d")
        remaining = (end_date - datetime.now()).days
        emoji = "🟢" if remaining > 7 else "🟡" if remaining > 3 else "🔴"
        text += f"{i}. {emoji} {sub[3]}\n"
        text += f"   📋 {get_plan_name(sub[5])} | ⏳ {remaining} يوم\n\n"
    
    if len(members) > 20:
        text += f"... و {len(members) - 20} مشترك آخر"
    
    keyboard = [[InlineKeyboardButton("🔙 رجوع", callback_data="back_main")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(text, reply_markup=reply_markup, parse_mode="Markdown")

async def show_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if not is_admin(query.from_user.id):
        return
    
    conn = get_db()
    c = conn.cursor()
    
    c.execute("SELECT COUNT(*) FROM subscriptions WHERE status='active'")
    active = c.fetchone()[0]
    
    c.execute("SELECT COUNT(*) FROM subscriptions WHERE status='expired'")
    expired = c.fetchone()[0]
    
    c.execute("SELECT COUNT(*) FROM subscriptions WHERE status='active' AND date(end_date) <= date('now', '+3 days')")
    expiring_soon = c.fetchone()[0]
    
    c.execute("SELECT plan, COUNT(*) FROM subscriptions WHERE status='active' GROUP BY plan")
    plans = c.fetchall()
    
    conn.close()
    
    plans_text = ""
    for plan, count in plans:
        plans_text += f"  • {get_plan_name(plan)}: {count}\n"
    
    keyboard = [[InlineKeyboardButton("🔙 رجوع", callback_data="back_main")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        f"📊 **إحصائيات الاشتراكات**\n\n"
        f"✅ فعالين: {active}\n"
        f"❌ منتهية: {expired}\n"
        f"⚠️ تنتهي خلال 3 أيام: {expiring_soon}\n\n"
        f"📋 **توزيع الخطط:**\n{plans_text}",
        reply_markup=reply_markup,
        parse_mode="Markdown"
    )

async def search_member(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if not is_admin(query.from_user.id):
        return
    
    context.user_data["searching"] = True
    await query.edit_message_text(
        "🔍 **البحث عن مشترك**\n\n"
        "أرسل ID المشترك أو اسمه:",
        parse_mode="Markdown"
    )

async def delete_subscription(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if not is_admin(query.from_user.id):
        return
    
    sub_id = query.data.replace("delete_", "")
    
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT * FROM subscriptions WHERE id=?", (sub_id,))
    sub = c.fetchone()
    
    if sub:
        c.execute("UPDATE subscriptions SET status='expired' WHERE id=?", (sub_id,))
        conn.commit()
        
        # طرد المستخدم من القناة
        if sub[1]:
            try:
                await context.bot.ban_chat_member(CHANNEL_ID, sub[1])
                await asyncio.sleep(1)
                await context.bot.unban_chat_member(CHANNEL_ID, sub[1])
                
                # إرسال إشعار للمشترك
                try:
                    await context.bot.send_message(
                        chat_id=sub[1],
                        text="❌ **تم إلغاء اشتراكك**\n\n"
                             "تواصل مع الأدمن لتجديد اشتراكك.",
                        parse_mode="Markdown"
                    )
                except:
                    pass
            except Exception as e:
                print(f"Error banning user: {e}")
    
    conn.close()
    
    await query.edit_message_text(
        f"✅ تم حذف الاشتراك وطرد المشترك من القناة!",
        parse_mode="Markdown"
    )

async def renew_subscription(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if not is_admin(query.from_user.id):
        return
    
    sub_id = query.data.replace("renew_", "")
    context.user_data["renewing_id"] = sub_id
    
    keyboard = [
        [InlineKeyboardButton("📅 يومي", callback_data=f"renewplan_daily_{sub_id}")],
        [InlineKeyboardButton("📆 أسبوعي", callback_data=f"renewplan_weekly_{sub_id}")],
        [InlineKeyboardButton("🗓️ شهري", callback_data=f"renewplan_monthly_{sub_id}")],
        [InlineKeyboardButton("🎯 سنوي", callback_data=f"renewplan_yearly_{sub_id}")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text("🔄 اختر خطة التجديد:", reply_markup=reply_markup)

async def do_renew(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    parts = query.data.split("_")
    plan = parts[1]
    sub_id = parts[2]
    
    days = get_plan_days(plan)
    new_end = (datetime.now() + timedelta(days=days)).strftime("%Y-%m-%d")
    
    conn = get_db()
    c = conn.cursor()
    c.execute("UPDATE subscriptions SET end_date=?, plan=?, status='active', notified_3days=0, notified_1day=0 WHERE id=?",
              (new_end, plan, sub_id))
    c.execute("SELECT * FROM subscriptions WHERE id=?", (sub_id,))
    sub = c.fetchone()
    conn.commit()
    conn.close()
    
    if sub and sub[1]:
        try:
            # إنشاء رابط جديد
            expire_date = datetime.now() + timedelta(days=days)
            invite = await context.bot.create_chat_invite_link(
                chat_id=CHANNEL_ID,
                member_limit=1,
                expire_date=expire_date
            )
            await context.bot.send_message(
                chat_id=sub[1],
                text=f"✅ **تم تجديد اشتراكك!**\n\n"
                     f"📋 الخطة: {get_plan_name(plan)}\n"
                     f"📅 ينتهي في: {new_end}\n\n"
                     f"🔗 رابط الدخول الجديد:\n{invite.invite_link}",
                parse_mode="Markdown"
            )
        except:
            pass
    
    await query.edit_message_text(
        f"✅ تم تجديد الاشتراك حتى {new_end}!",
        parse_mode="Markdown"
    )

async def back_main(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    keyboard = [
        [InlineKeyboardButton("➕ إضافة مشترك جديد", callback_data="add_member")],
        [InlineKeyboardButton("📋 قائمة المشتركين", callback_data="list_members")],
        [InlineKeyboardButton("📊 إحصائيات", callback_data="stats")],
        [InlineKeyboardButton("🔍 بحث عن مشترك", callback_data="search_member")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(
        "🎛️ **لوحة تحكم الاشتراكات**\n\n"
        "اختر ما تريد:",
        reply_markup=reply_markup,
        parse_mode="Markdown"
    )

# ==================== التحقق التلقائي من الاشتراكات ====================
async def check_subscriptions(context: ContextTypes.DEFAULT_TYPE):
    conn = get_db()
    c = conn.cursor()
    
    today = datetime.now().strftime("%Y-%m-%d")
    
    # المشتركون اللي ينتهي اشتراكهم خلال 3 أيام
    c.execute("""
        SELECT * FROM subscriptions 
        WHERE status='active' 
        AND date(end_date) <= date('now', '+3 days')
        AND date(end_date) > date('now')
        AND notified_3days=0
    """)
    expiring_3days = c.fetchall()
    
    for sub in expiring_3days:
        end_date = sub[7]
        remaining = (datetime.strptime(end_date, "%Y-%m-%d") - datetime.now()).days + 1
        
        # تنبيه المشترك
        if sub[1]:
            try:
                await context.bot.send_message(
                    chat_id=sub[1],
                    text=f"⚠️ **تنبيه انتهاء الاشتراك**\n\n"
                         f"اشتراكك سينتهي خلال {remaining} يوم\n"
                         f"📅 تاريخ الانتهاء: {end_date}\n\n"
                         "تواصل مع الأدمن لتجديد اشتراكك.",
                    parse_mode="Markdown"
                )
            except:
                pass
        
        # تنبيه الأدمن
        try:
            await context.bot.send_message(
                chat_id=ADMIN_ID,
                text=f"⚠️ **تنبيه:** اشتراك {sub[3]} سينتهي خلال {remaining} يوم\n"
                     f"🆔 ID: {sub[1]}\n"
                     f"📅 النهاية: {end_date}",
                parse_mode="Markdown"
            )
        except:
            pass
        
        c.execute("UPDATE subscriptions SET notified_3days=1 WHERE id=?", (sub[0],))
    
    # المشتركون اللي ينتهي اشتراكهم اليوم
    c.execute("""
        SELECT * FROM subscriptions 
        WHERE status='active' 
        AND date(end_date) = date('now')
        AND notified_1day=0
    """)
    expiring_today = c.fetchall()
    
    for sub in expiring_today:
        if sub[1]:
            try:
                await context.bot.send_message(
                    chat_id=sub[1],
                    text="🚨 **اشتراكك ينتهي اليوم!**\n\n"
                         "تواصل مع الأدمن فوراً لتجديد اشتراكك وإلا ستُطرد من القناة.",
                    parse_mode="Markdown"
                )
            except:
                pass
        
        try:
            await context.bot.send_message(
                chat_id=ADMIN_ID,
                text=f"🚨 **اشتراك {sub[3]} ينتهي اليوم!**\n"
                     f"🆔 ID: {sub[1]}",
                parse_mode="Markdown"
            )
        except:
            pass
        
        c.execute("UPDATE subscriptions SET notified_1day=1 WHERE id=?", (sub[0],))
    
    # المشتركون المنتهية اشتراكاتهم - طرد تلقائي
    c.execute("""
        SELECT * FROM subscriptions 
        WHERE status='active' 
        AND date(end_date) < date('now')
    """)
    expired = c.fetchall()
    
    for sub in expired:
        # طرد من القناة
        if sub[1]:
            try:
                await context.bot.ban_chat_member(CHANNEL_ID, sub[1])
                await asyncio.sleep(1)
                await context.bot.unban_chat_member(CHANNEL_ID, sub[1])
                
                await context.bot.send_message(
                    chat_id=sub[1],
                    text="❌ **انتهى اشتراكك**\n\n"
                         "تم طردك من القناة لانتهاء اشتراكك.\n"
                         "تواصل مع الأدمن لتجديد اشتراكك.",
                    parse_mode="Markdown"
                )
            except:
                pass
            
            # إشعار الأدمن
            try:
                await context.bot.send_message(
                    chat_id=ADMIN_ID,
                    text=f"🚫 **تم طرد {sub[3]} من القناة**\n"
                         f"🆔 ID: {sub[1]}\n"
                         f"📅 انتهى في: {sub[7]}",
                    parse_mode="Markdown"
                )
            except:
                pass
        
        c.execute("UPDATE subscriptions SET status='expired' WHERE id=?", (sub[0],))
    
    conn.commit()
    conn.close()

# ==================== تشغيل البوت ====================
def main():
    init_db()
    
    app = Application.builder().token(BOT_TOKEN).build()
    
    # أوامر
    app.add_handler(CommandHandler("start", start))
    
    # Callbacks
    app.add_handler(CallbackQueryHandler(add_member_start, pattern="^add_member$"))
    app.add_handler(CallbackQueryHandler(list_members, pattern="^list_members$"))
    app.add_handler(CallbackQueryHandler(show_stats, pattern="^stats$"))
    app.add_handler(CallbackQueryHandler(search_member, pattern="^search_member$"))
    app.add_handler(CallbackQueryHandler(choose_plan, pattern="^plan_"))
    app.add_handler(CallbackQueryHandler(delete_subscription, pattern="^delete_"))
    app.add_handler(CallbackQueryHandler(renew_subscription, pattern="^renew_[0-9]"))
    app.add_handler(CallbackQueryHandler(do_renew, pattern="^renewplan_"))
    app.add_handler(CallbackQueryHandler(back_main, pattern="^back_main$"))
    
    # رسائل نصية
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    # فحص الاشتراكات كل ساعة
    app.job_queue.run_repeating(check_subscriptions, interval=3600, first=10)
    
    print("✅ البوت يعمل...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
