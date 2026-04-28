import httpx
from config import PLISIO_API_KEY

# Base URLs
CREATE_URL = "https://plisio.net/api/v1/invoices/new"
DETAIL_URL = "https://plisio.net/api/v1/operations/{}"

async def create_plisio_invoice(amount, currency, order_id, user_id):
    # Mapping to ensure USDT uses the correct Plisio CID (e.g. USDT_TRC20)
    # If the user chose USDT, we must tell Plisio which network.
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
        # 🎯 THE MAGIC PARAMETER: This forces Plisio to ONLY show this coin
        # and skips the selection gallery entirely.
        'allowed_psys_cids': coin_id, 
        'plugin': 'telegram_bot_v1',
    }

    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(CREATE_URL, params=params, timeout=15)
            create_data = response.json()
            
            if create_data.get('status') == 'success':
                txn_id = create_data['data']['txn_id']
                # With allowed_psys_cids set, this URL goes straight to the QR code
                invoice_url = create_data['data']['invoice_url']

                # Step 2: Get details for the coin_amount
                detail_res = await client.get(
                    DETAIL_URL.format(txn_id), 
                    params={'api_key': PLISIO_API_KEY}, 
                    timeout=10
                )
                detail_data = detail_res.json()
                coin_amount = detail_data['data'].get('amount', "Check Link") if detail_data.get('status') == 'success' else "Check Link"

                return invoice_url, coin_amount
            
            print(f"❌ Plisio Error: {create_data.get('data')}")
            return None, None
        except Exception as e:
            print(f"❌ API Failure: {e}")
            return None, None