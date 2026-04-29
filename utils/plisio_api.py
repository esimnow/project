import httpx
from config import PLISIO_API_KEY

CREATE_URL = "https://plisio.net/api/v1/invoices/new"

async def create_plisio_invoice(amount, currency, order_id, user_id):
    coin_id = currency.upper() 
    if coin_id == "USDT": 
        coin_id = "USDT_TRC20"

    params = {
        'api_key': PLISIO_API_KEY,
        'currency': coin_id,
        'order_name': f"Deposit_{order_id}",
        'order_number': str(order_id),
        'source_amount': str(amount),
        'source_currency': 'USD',
        'email': f"user_{user_id}@bot.com",
        'allowed_psys_cids': coin_id, 
        'plugin': 'telegram_bot_v1',
    }

    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(CREATE_URL, params=params, timeout=15)
            create_data = response.json()
            
            if create_data.get('status') == 'success':
                invoice_url = create_data['data']['invoice_url']
                
                # 🎯 THE FIX: Plisio includes the exact crypto amount in this first response
                coin_amount = create_data['data'].get('amount', 'Check Link')

                return invoice_url, coin_amount
            
            print(f"❌ Plisio Error: {create_data.get('data')}")
            return None, None
        except Exception as e:
            print(f"❌ API Failure: {e}")
            return None, None