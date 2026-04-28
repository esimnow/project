import logging
import asyncio
from fastapi import FastAPI, Request, BackgroundTasks
import uvicorn
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters
from telegram.request import HTTPXRequest 

from config import BOT_TOKEN
from utils.db import init_db, close_db, complete_deposit
from handlers.start import start
from handlers.router import purchase_router,admin_router

# 1. Setup logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

# 2. FastAPI Setup
app = FastAPI()
telegram_app = None

@app.on_event("startup")
async def startup_event():
    """This runs when the server starts"""
    global telegram_app
    init_db()
    
    # Configure Bot
    request_config = HTTPXRequest(connect_timeout=30, read_timeout=30)
    telegram_app = (
        ApplicationBuilder()
        .token(BOT_TOKEN)
        .request(request_config)
        .build()
    )

    # Register Handlers
    telegram_app.add_handler(CommandHandler("start", start))
    telegram_app.add_handler(purchase_router)
    telegram_app.add_handler(admin_router)

    # Initialize and start the bot in the background
    await telegram_app.initialize()
    await telegram_app.updater.start_polling()
    await telegram_app.start()
    print("🚀 Bot & FastAPI are live on Railway!")

@app.on_event("shutdown")
async def shutdown_event():
    """This runs when the server stops"""
    await telegram_app.stop()
    await telegram_app.updater.stop()
    await telegram_app.shutdown()
    close_db()

@app.post("/plisio/webhook")
async def plisio_webhook(request: Request):
    """Handles incoming payment confirmations"""
    # Plisio sends Form Data, not JSON
    form_data = await request.form()
    order_id = form_data.get("order_number")
    status = form_data.get("status")

    print(f"📩 Webhook: Order {order_id} is {status}")

    if status == 'completed':
        # 🎯 Update PostgreSQL
        result = complete_deposit(order_id)
        
        if result and telegram_app:
            user_id, amount = result
            # 🚀 No threading needed! We just call the bot directly
            await telegram_app.bot.send_message(
                chat_id=user_id,
                text=f"✅ <b>Deposit Confirmed!</b>\nAdded <b>${amount:.2f}</b> to your balance.",
                parse_mode="HTML"
            )
            
    return {"status": "ok"}

if __name__ == "__main__":
    # For local testing
    uvicorn.run(app, host="0.0.0.0", port=5000)