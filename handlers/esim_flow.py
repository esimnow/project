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

# 🛑 UNIVERSAL STATE MAP - DO NOT CHANGE NUMBERS
(
    SELECTING_REGION, 
    SELECTING_PLAN, 
    DEPOSITING, 
    ENTERING_AMOUNT, 
    CHOOSING_COIN, 
    CONFIRMING_ORDER,
    WAITING_FOR_PAYMENT,
    INTERCEPTING
) = range(8)


async def handle_buy_esim(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    # 🛡️ THE GATEKEEPER: Check for unpaid orders first
    pending = check_and_get_pending_order(user_id)
    if pending:
        # If found, trap them in the INTERCEPTING state
        return await show_interceptor_screen(update, context, pending, next_action="buyesim")

    # If clean, proceed to the normal menu
    await update.message.reply_text(
        "🌍 <b>Select Region</b>\nChoose the area for your eSIM:",
        reply_markup=region_menu(),
        parse_mode="HTML"
    )
    return SELECTING_REGION

async def handle_usa_selected(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        "🇺🇸 <b>USA eSIM Plans</b>\nSelect your duration:",
        reply_markup=plan_menu(),
        parse_mode="HTML"
    )
    return SELECTING_PLAN

async def handle_plan_selected(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    balance = get_user_balance(user_id) or 0.0
    
    plan_data = {
        "plan_1m": {"price": 10.00, "name": "1 Month"},
        "plan_2m": {"price": 18.00, "name": "2 Months"},
        "plan_3m": {"price": 25.00, "name": "3 Months"},
        "plan_6m": {"price": 45.00, "name": "6 Months"},
        "plan_1y": {"price": 80.00, "name": "1 Year"}
    }
    
    selected = plan_data.get(query.data, plan_data["plan_1m"])
    price = selected["price"]
    duration = selected["name"]

    while True:
        order_id = random.randint(10000000, 99999999)
        if is_order_id_unique(order_id): break
    
    context.user_data['pending_order'] = {
        'order_id': order_id, 'price': price, 'region': "USA", 'duration': duration
    }

    summary_text = (
        f"📋 <b>Order Summary</b>\n━━━━━━━━━━━━━━━━━━\n"
        f"<b>Order ID:</b> <code>{order_id}</code>\n"
        f"📍 <b>Region:</b> USA\n"
        f"⏱️ <b>Duration:</b> {duration}\n"
        f"💰 <b>Price:</b> ${price:.2f}\n"
        f"💵 <b>Your Balance:</b> ${balance:.2f}\n━━━━━━━━━━━━━━━━━━\n"
    )

    if balance >= price:
        summary_text += "<b>Confirm this purchase?</b>"
        btns = [[InlineKeyboardButton("✅ Confirm", callback_data="confirm_final"),
                 InlineKeyboardButton("❌ Cancel", callback_data="back_to_main")]]
    else:
        top_up_amount = price - balance
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
        # 1. Execute Database Transactions
        create_order_record(
            order['order_id'], 
            user_id, 
            order['price'], 
            order['region'], 
            order['duration']
        )
        deduct_user_balance(user_id, order['price'])

        # 2. The High-End Visual UI for the User
        success_text = (
            f"🥳 <b>Purchase Successful!</b>\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"🧾 <b>Order ID:</b> <code>{order['order_id']}</code>\n"
            f"📦 <b>Item:</b> {order['region']} ({order['duration']})\n"
            f"💰 <b>Paid:</b> ${order['price']:.2f}\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"📥 Your eSIM QR code will be sent here in a moment..."
        )
        await query.edit_message_text(success_text, parse_mode="HTML")

        # 🎯 3. THE ADMIN TOPIC GENERATOR
        if PENDING_GROUP_ID:
            try:
                # A. Create the new Topic in the Pending Group
                topic = await context.bot.create_forum_topic(
                    chat_id=PENDING_GROUP_ID,
                    name=f"#{order['order_id']} | {order['region']}"
                )
                
                # B. Build the Work Order Summary
                admin_text = (
                    f"🚨 <b>NEW ORDER PENDING</b>\n"
                    f"━━━━━━━━━━━━━━━━━━\n"
                    f"👤 <b>User ID:</b> <code>{user_id}</code>\n"
                    f"🧾 <b>Order ID:</b> <code>{order['order_id']}</code>\n"
                    f"📦 <b>Plan:</b> {order['region']} ({order['duration']})\n"
                    f"💰 <b>Paid:</b> ${order['price']:.2f}\n"
                    f"━━━━━━━━━━━━━━━━━━\n"
                    f"<i>Click below to fulfill the eSIM details.</i>"
                )
                
                admin_markup = InlineKeyboardMarkup([[
                    InlineKeyboardButton("🚀 Fulfill Order", callback_data=f"fulfill_{order['order_id']}")
                ]])
                
                # C. Route the message to the specific thread ID
                await context.bot.send_message(
                    chat_id=PENDING_GROUP_ID,
                    message_thread_id=topic.message_thread_id,
                    text=admin_text,
                    reply_markup=admin_markup,
                    parse_mode="HTML"
                )
            except Exception as admin_e:
                print(f"⚠️ Failed to create admin topic: {admin_e}")
        
    except Exception as e:
        print(f"❌ Purchase Error: {e}")
        await query.edit_message_text("⚠️ An error occurred during processing. Please contact support.")

    return ConversationHandler.END

async def back_to_main(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.delete_message()
    await context.bot.send_message(chat_id=update.effective_chat.id, text="Back to main menu.", reply_markup=main_menu_keyboard())
    return ConversationHandler.END