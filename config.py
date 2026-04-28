import os
from dotenv import load_dotenv

load_dotenv() # This loads the .env file

BOT_TOKEN = os.getenv("BOT_TOKEN")
DATABASE_URL = os.getenv("DATABASE_URL")
PLISIO_API_KEY = os.getenv("PLISIO_API_KEY")
ADMIN_IDS = [int(i.strip()) for i in os.getenv("ADMIN_IDS", "").split(",") if i.strip()]
PUBLIC_BASE_URL = os.getenv("PUBLIC_BASE_URL")
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET")
PENDING_GROUP_ID = os.getenv("PENDING_GROUP_ID")
DELIVERED_GROUP_ID = os.getenv("DELIVERED_GROUP_ID")