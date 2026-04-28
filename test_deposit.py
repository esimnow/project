import requests

# 1. SETTINGS
# If testing locally, use your localhost URL
# If testing the live Railway/ngrok version, use that URL
WEBHOOK_URL = "http://localhost:5000/plisio/webhook"

# 🎯 CRITICAL: Put an Order ID that actually exists in your 'transactions' table!
# You get this by going to your bot and starting a deposit.
FAKE_ORDER_ID = "90631841" 

# 2. THE MOCK DATA
# This matches the dictionary format Plisio sends in a real IPN
mock_data = {
    "order_number": FAKE_ORDER_ID,
    "status": "completed",
    "amount": "10.00",
    "currency": "USD",
    "txn_id": "MOCK_TXN_999"
}

def send_fake_payment():
    print(f"🚀 Sending fake 'completed' status for Order: {FAKE_ORDER_ID}...")
    try:
        # We use 'data=' because Plisio sends a Form-Encoded POST request
        response = requests.post(WEBHOOK_URL, data=mock_data)
        
        if response.status_code == 200:
            print("✅ Webhook delivered! Check your Bot terminal and Telegram.")
        else:
            print(f"❌ Failed. Server returned: {response.status_code}")
            print(f"Response: {response.text}")
            
    except Exception as e:
        print(f"🔥 Error connecting to Flask: {e}")

if __name__ == "__main__":
    send_fake_payment()