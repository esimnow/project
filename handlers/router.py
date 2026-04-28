from telegram.ext import (
    MessageHandler, 
    filters, 
    ConversationHandler, 
    CommandHandler, 
    CallbackQueryHandler
)
from handlers.esim_flow import (
    handle_buy_esim, handle_usa_selected, handle_plan_selected, handle_final_purchase, back_to_main,
    SELECTING_REGION, SELECTING_PLAN, CONFIRMING_ORDER
)
from handlers.wallet_flow import (
    handle_wallet, start_topup, 
    receive_amount, process_crypto_payment,
    show_usdt_networks, back_to_coins,
    handle_cancel_payment
)
from handlers.states import (
    SELECTING_REGION, SELECTING_PLAN, DEPOSITING, 
    ENTERING_AMOUNT, CHOOSING_COIN, CONFIRMING_ORDER, 
    WAITING_FOR_PAYMENT
)

async def debug_fallback(update, context):
    query = update.callback_query
    # Correctly grab the state to see where the user is stuck
    current_state = context.user_data.get('state') 
    print(f"👻 Ignored Click: {query.data} | Bot is in State: {current_state}")
    await query.answer("This button is not active right now.", show_alert=False)
    return None # None tells the bot to stay in the current room

purchase_router = ConversationHandler(
    entry_points=[
        MessageHandler(filters.Regex("^🌍 Buy eSIM$"), handle_buy_esim),
        MessageHandler(filters.Regex("^💰 Credits$"), handle_wallet)
    ],
    states={
        SELECTING_REGION: [
            CallbackQueryHandler(handle_usa_selected, pattern="^region_usa$"),
            CallbackQueryHandler(back_to_main, pattern="^back_to_main$")
        ],
        SELECTING_PLAN: [
            CallbackQueryHandler(handle_plan_selected, pattern="^plan_"),
            CallbackQueryHandler(handle_buy_esim, pattern="^back_to_regions$")
        ],
        DEPOSITING: [
            CallbackQueryHandler(start_topup, pattern="^start_topup$"),
            CallbackQueryHandler(back_to_main, pattern="^back_to_main$")
        ],
        ENTERING_AMOUNT: [
            MessageHandler(filters.TEXT & ~filters.COMMAND, receive_amount)
        ],
        CHOOSING_COIN: [
            CallbackQueryHandler(show_usdt_networks, pattern="^show_usdt_networks$"),
            CallbackQueryHandler(back_to_coins, pattern="^back_to_coins$"),
            CallbackQueryHandler(process_crypto_payment, pattern="^pay_"), 
            CallbackQueryHandler(start_topup, pattern="^start_topup$"),
            CallbackQueryHandler(back_to_main, pattern="^back_to_main$")
        ],
        CONFIRMING_ORDER: [
            CallbackQueryHandler(handle_final_purchase, pattern="^confirm_final$"),
            CallbackQueryHandler(start_topup, pattern="^start_topup$"), 
            CallbackQueryHandler(handle_wallet, pattern="^view_wallet$"),
            CallbackQueryHandler(back_to_main, pattern="^back_to_main$")
        ],
        # 🎯 ROOM 6: LISTEN FOR THE CANCEL BUTTON
        WAITING_FOR_PAYMENT: [
            CallbackQueryHandler(handle_cancel_payment, pattern="^cancel_pay_"),
            CallbackQueryHandler(back_to_main, pattern="^back_to_main$")
        ]
    },
    fallbacks=[
        CommandHandler("cancel", back_to_main),
        CallbackQueryHandler(debug_fallback)
    ],
    allow_reentry=True
)