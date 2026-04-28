from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler
from config import PENDING_GROUP_ID, DELIVERED_GROUP_ID
from utils.db import save_delivery_details, get_order_by_code
from handlers.states import ADMIN_SMDP, ADMIN_ACTIVATION, ADMIN_QR, ADMIN_CONFIRM

async def start_fulfill(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Step 1: Admin clicks Fulfill inside the Pending Topic"""
    query = update.callback_query
    await query.answer()
    
    # Extract order_id from callback (e.g., fulfill_90631841)
    order_id = query.data.split("_")[1]
    
    # Initialize the admin's clipboard
    context.user_data['admin_order_id'] = order_id
    context.user_data['admin_delivery'] = {}

    text = (
        f"⚙️ **Fulfilling Order #{order_id}**\n\n"
        f"**Step 1 of 3:**\n"
        f"📝 Please paste the **SM-DP+ Address** below."
    )
    markup = InlineKeyboardMarkup([[InlineKeyboardButton("⏭️ Skip (Leave Blank)", callback_data="skip_smdp")]])
    
    await query.edit_message_text(text, reply_markup=markup, parse_mode="Markdown")
    return ADMIN_SMDP

async def receive_smdp(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Step 2: Save SM-DP+ and ask for Activation Code"""
    query = update.callback_query
    
    if query:
        await query.answer()
        context.user_data['admin_delivery']['smdp'] = "N/A"
        message = query.message
    else:
        context.user_data['admin_delivery']['smdp'] = update.message.text
        message = update.message

    text = "**Step 2 of 3:**\n🔑 Please paste the **Activation Code** below."
    markup = InlineKeyboardMarkup([[InlineKeyboardButton("⏭️ Skip (Leave Blank)", callback_data="skip_activation")]])
    
    await message.reply_text(text, reply_markup=markup, parse_mode="Markdown")
    return ADMIN_ACTIVATION

async def receive_activation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Step 3: Save Activation and ask for QR Code"""
    query = update.callback_query
    
    if query:
        await query.answer()
        context.user_data['admin_delivery']['activation'] = "N/A"
        message = query.message
    else:
        context.user_data['admin_delivery']['activation'] = update.message.text
        message = update.message

    text = "**Step 3 of 3:**\n📷 Please **Upload the QR Code image** now."
    markup = InlineKeyboardMarkup([[InlineKeyboardButton("⏭️ Skip (No QR)", callback_data="skip_qr")]])
    
    await message.reply_text(text, reply_markup=markup, parse_mode="Markdown")
    return ADMIN_QR

async def receive_qr(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Step 4: Save QR and Show the Final Preview"""
    query = update.callback_query
    
    if query:
        await query.answer()
        context.user_data['admin_delivery']['qr_file_id'] = None
        message = query.message
    else:
        # Grab the highest resolution version of the uploaded photo
        context.user_data['admin_delivery']['qr_file_id'] = update.message.photo[-1].file_id
        message = update.message

    order_id = context.user_data['admin_order_id']
    delivery = context.user_data['admin_delivery']

    text = (
        f"🔍 **PREVIEW: Delivery for #{order_id}**\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"**SM-DP+ Address:** `{delivery['smdp']}`\n"
        f"**Activation Code:** `{delivery['activation']}`\n"
        f"**QR Included:** {'✅ Yes' if delivery['qr_file_id'] else '❌ No'}\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"⚠️ *Please review carefully before sending to the user.*"
    )
    
    markup = InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Confirm & Send to User", callback_data="confirm_delivery")],
        [InlineKeyboardButton("🔙 Edit Details", callback_data=f"fulfill_{order_id}")],
        [InlineKeyboardButton("❌ Cancel", callback_data="cancel_wizard")]
    ])
    
    await message.reply_text(text, reply_markup=markup, parse_mode="Markdown")
    return ADMIN_CONFIRM

async def confirm_delivery(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Final Step: Executes DB save, notifies user, and relocates the topic."""
    query = update.callback_query
    await query.answer()
    
    order_id = context.user_data['admin_order_id']
    delivery = context.user_data['admin_delivery']
    current_thread_id = update.effective_message.message_thread_id
    
    # 1. Update Database
    save_delivery_details(order_id, delivery['smdp'], delivery['activation'], delivery['qr_file_id'])
    user_id, price, region, duration, status = get_order_by_code(order_id)

    # 2. Send to User
    # 📌 NOTE: You can replace this block later with your custom PDF generation!
    user_text = (
        f"📦 **Your eSIM for {region} has arrived!**\n\n"
        f"**Order ID:** `#{order_id}`\n"
        f"**SM-DP+ Address:** `{delivery['smdp']}`\n"
        f"**Activation Code:** `{delivery['activation']}`\n\n"
        f"Thank you for choosing us! Need help? Contact Support."
    )
    
    try:
        if delivery['qr_file_id']:
            await context.bot.send_photo(chat_id=user_id, photo=delivery['qr_file_id'], caption=user_text, parse_mode="Markdown")
        else:
            await context.bot.send_message(chat_id=user_id, text=user_text, parse_mode="Markdown")
    except Exception as e:
        await query.message.reply_text(f"⚠️ Failed to DM user {user_id}. They might have blocked the bot.")

    # 3. Relocate to Delivered Group
    try:
        # A. Create new topic in the Delivered group
        new_topic = await context.bot.create_forum_topic(
            chat_id=DELIVERED_GROUP_ID,
            name=f"✅ #{order_id} | {region}"
        )
        
        # B. Post the receipt there with the Phase 5 Edit button
        admin_receipt = (
            f"✅ **ORDER DELIVERED**\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"👤 **User ID:** `{user_id}`\n"
            f"🧾 **Order ID:** `#{order_id}`\n"
            f"SM-DP+: `{delivery['smdp']}`\n"
            f"Activation: `{delivery['activation']}`\n"
            f"━━━━━━━━━━━━━━━━━━"
        )
        markup = InlineKeyboardMarkup([[InlineKeyboardButton("✏️ Edit & Resend", callback_data=f"editdelivery_{order_id}")]])
        
        if delivery['qr_file_id']:
            await context.bot.send_photo(chat_id=DELIVERED_GROUP_ID, message_thread_id=new_topic.message_thread_id, photo=delivery['qr_file_id'], caption=admin_receipt, reply_markup=markup, parse_mode="Markdown")
        else:
            await context.bot.send_message(chat_id=DELIVERED_GROUP_ID, message_thread_id=new_topic.message_thread_id, text=admin_receipt, reply_markup=markup, parse_mode="Markdown")

        # C. Delete the old topic from the Pending group to keep it clean
        await context.bot.delete_forum_topic(chat_id=PENDING_GROUP_ID, message_thread_id=current_thread_id)

    except Exception as e:
        print(f"Topic Relocation Error: {e}")
        await query.edit_message_text(f"✅ Delivered to user, but failed to move topic: {e}")

    return ConversationHandler.END

async def cancel_wizard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Aborts the admin input process."""
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("❌ **Fulfillment Canceled.** The order remains pending.")
    return ConversationHandler.END