import random
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler
from menus.catalog_menus import region_menu, plan_menu
from menus.main_menu import main_menu_keyboard
from handlers.interceptor import show_interceptor_screen
from config import PENDING_GROUP_ID
from utils.db import (
    get_user_balance, 
    is_order_id_unique, 
    create_order_record, 
    deduct_user_balance,
    check_and_get_pending_order
)

# 🛑 UNIVERSAL STATE MAP - MATCHING YOUR CODE
(
    SELECTING_REGION, 
    SELECTING_PLAN, 
    DEPOSITING, 
    ENTERING_AMOUNT, 
    CHOOSING_COIN, 
    CONFIRMING_ORDER,
    WAITING_FOR_PAYMENT,
    INTERCEPTING,
    SELECT_RENEWAL_TYPE
) = range(9)

async def handle_buy_esim(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    pending = check_and_get_pending_order(user_id)
    if pending:
        return await show_interceptor_screen(update, context, pending, next_action="buyesim")

    await update.message.reply_text(
        "🌍 <b>Select Region</b>\nChoose the area for your eSIM:",
        reply_markup=region_menu(),
        parse_mode="HTML"
    )
    return SELECTING_REGION

async def handle_usa_selected(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """User clicked the 'region_usa' button"""
    query = update.callback_query
    await query.answer()
    
    context.user_data['selected_region'] = 'usa'
    
    text = (
        "<b>🇺🇸 USA eSIM Configuration</b>\n\n"
        "Please choose your plan type:\n\n"
        "• <b>🔄 Renewable:</b> Can be Renewed / extended Once Expired.\n"
        "• <b>🚫 Non-Renewable:</b> Cannot Renew eSIM Once Plans End.\n\n"
        "<i>💰 Note: Renewable plans have an additional $2.00 fee.</i>"
    )
    
    await query.edit_message_text(
        text=text,
        reply_markup=renewal_type_keyboard(),
        parse_mode="HTML"
    )
    return SELECT_RENEWAL_TYPE

def renewal_type_keyboard():
    keyboard = [
        [
            InlineKeyboardButton("🔄 Renewable (+$2)", callback_data="renewal_true"),
            InlineKeyboardButton("🚫 Non-Renewable", callback_data="renewal_false")
        ],
        [InlineKeyboardButton("⬅️ Back to Regions", callback_data="back_to_regions")]
    ]
    return InlineKeyboardMarkup(keyboard)

async def handle_renewal_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    # Save the renewal choice
    context.user_data['is_renewable'] = (query.data == "renewal_true")
    
    await query.edit_message_text(
        text="📅 <b>Select Plan Duration:</b>\n\nChoose your preferred time period:",
        reply_markup=plan_menu(),
        parse_mode="HTML"
    )
    return SELECTING_PLAN

async def handle_plan_selected(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    balance = get_user_balance(user_id) or 0.0
    
    # 🎯 Get renewal status for fee calculation
    is_renewable = context.user_data.get('is_renewable', False)
    renewal_fee = 2.00 if is_renewable else 0.00
    
    plan_data = {
        "plan_1m": {"price": 10.00, "name": "1 Month"},
        "plan_2m": {"price": 18.00, "name": "2 Months"},
        "plan_3m": {"price": 25.00, "name": "3 Months"},
        "plan_6m": {"price": 45.00, "name": "6 Months"},
        "plan_1y": {"price": 80.00, "name": "1 Year"}
    }
    
    selected = plan_data.get(query.data, plan_data["plan_1m"])
    # 🎯 Add the $2 fee if applicable
    total_price = selected["price"] + renewal_fee
    duration = selected["name"]

    while True:
        order_id = random.randint(10000000, 99999999)
        if is_order_id_unique(order_id): break
    
    context.user_data['pending_order'] = {
        'order_id': order_id, 
        'price': total_price, 
        'region': "USA", 
        'duration': duration,
        'is_renewable': is_renewable
    }

    renewal_label = "🔄 Renewable" if is_renewable else "🚫 Non-Renewable"
    summary_text = (
        f"📋 <b>Order Summary</b>\n━━━━━━━━━━━━━━━━━━\n"
        f"<b>Order ID:</b> <code>{order_id}</code>\n"
        f"📍 <b>Region:</b> USA\n"
        f"⚙️ <b>Type:</b> {renewal_label}\n"
        f"⏱️ <b>Duration:</b> {duration}\n"
        f"💰 <b>Total Price:</b> ${total_price:.2f}\n"
        f"💵 <b>Your Balance:</b> ${balance:.2f}\n━━━━━━━━━━━━━━━━━━\n"
    )

    if balance >= total_price:
        summary_text += "<b>Confirm this purchase?</b>"
        btns = [[InlineKeyboardButton("✅ Confirm", callback_data="confirm_final"),
                 InlineKeyboardButton("❌ Cancel", callback_data="back_to_main")]]
    else:
        top_up_amount = total_price - balance
        summary_text += f"❗ <b>Top up:</b> ${top_up_amount:.2f}\n\n<b>Insufficient funds.</b>"
        btns = [[InlineKeyboardButton("💎 Top Up", callback_data="view_wallet"),
                 InlineKeyboardButton("❌ Cancel", callback_data="back_to_main")]]

    await query.edit_message_text(summary_text, reply_markup=InlineKeyboardMarkup(btns), parse_mode="HTML")
    return CONFIRMING_ORDER

async def handle_final_purchase(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    order = context.user_data.get('pending_order')

    if not order:
        await query.edit_message_text("❌ Error: Order session expired. Please start over.")
        return ConversationHandler.END

    try:
        # 🎯 1. Save to DB with Renewable Boolean
        create_order_record(
            order['order_id'], 
            user_id, 
            order['price'], 
            order['region'], 
            order['duration'],
            order['is_renewable'] # Ensure your DB function handles this!
        )
        deduct_user_balance(user_id, order['price'])

        renewal_status = "🔄 RENEWABLE" if order['is_renewable'] else "🚫 NON-RENEWABLE"

        # 2. User Success UI
        success_text = (
            f"🥳 <b>Purchase Successful!</b>\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"🧾 <b>Order ID:</b> <code>{order['order_id']}</code>\n"
            f"📦 <b>Item:</b> {order['region']} ({order['duration']})\n"
            f"⚙️ <b>Type:</b> {renewal_status}\n"
            f"💰 <b>Paid:</b> ${order['price']:.2f}\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"📥 Your eSIM QR code will be sent here in a moment..."
        )
        await query.edit_message_text(success_text, parse_mode="HTML")

        # 🎯 3. ADMIN ALERT WITH RENEWAL INFO
        if PENDING_GROUP_ID:
            try:
                topic = await context.bot.create_forum_topic(
                    chat_id=PENDING_GROUP_ID,
                    name=f"#{order['order_id']} | {renewal_status}"
                )
                
                admin_text = (
                    f"🚨 <b>NEW ORDER PENDING</b>\n"
                    f"━━━━━━━━━━━━━━━━━━\n"
                    f"👤 <b>User ID:</b> <code>{user_id}</code>\n"
                    f"🧾 <b>Order ID:</b> <code>{order['order_id']}</code>\n"
                    f"📦 <b>Plan:</b> {order['region']} ({order['duration']})\n"
                    f"⚙️ <b>Type:</b> {renewal_status}\n"
                    f"💰 <b>Paid:</b> ${order['price']:.2f}\n"
                    f"━━━━━━━━━━━━━━━━━━\n"
                    f"<i>Click below to fulfill the eSIM details.</i>"
                )
                
                admin_markup = InlineKeyboardMarkup([[
                    InlineKeyboardButton("🚀 Fulfill Order", callback_data=f"fulfill_{order['order_id']}")
                ]])
                
                await context.bot.send_message(
                    chat_id=PENDING_GROUP_ID,
                    message_thread_id=topic.message_thread_id,
                    text=admin_text,
                    reply_markup=admin_markup,
                    parse_mode="HTML"
                )
            except Exception as admin_e:
                print(f"⚠️ Admin Alert Error: {admin_e}")
        
    except Exception as e:
        print(f"❌ Purchase Error: {e}")
        await query.edit_message_text("⚠️ Processing error. Contact support.")

    return ConversationHandler.END

async def back_to_main(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.delete_message()
    await context.bot.send_message(chat_id=update.effective_chat.id, text="Back to main menu.", reply_markup=main_menu_keyboard())
    return ConversationHandler.END