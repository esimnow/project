from telegram import ReplyKeyboardMarkup, KeyboardButton

def main_menu_keyboard():
    # We group them: 2 buttons in the first list, 2 in the second.
    keyboard = [
        [KeyboardButton("🌍 Buy eSIM"), KeyboardButton("💰 Credits")],
        [KeyboardButton("📊 My Orders"), KeyboardButton("🛠️ Support")]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)