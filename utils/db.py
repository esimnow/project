import psycopg
from psycopg.rows import dict_row
import os 
from psycopg_pool import ConnectionPool
from config import DATABASE_URL

# Setup the connection pool
db_pool = ConnectionPool(
    conninfo=DATABASE_URL,
    min_size=1,
    max_size=10,
    timeout=30.0
)

DB_URL = os.getenv("DATABASE_URL")

def get_connection():
    """Borrow a connection from the pool"""
    return db_pool.connection()

def init_db():
    with get_connection() as conn:
        with conn.cursor() as cur:
            # 1. Users Table
            cur.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    user_id BIGINT PRIMARY KEY,
                    username TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)
            cur.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS balance DECIMAL(10, 2) DEFAULT 0.0;")

            # 2. Orders Table (WITH THE MISSING COLUMNS ADDED)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS orders (
                    id SERIAL PRIMARY KEY,
                    user_id BIGINT REFERENCES users(user_id),
                    order_code TEXT UNIQUE,
                    description TEXT,
                    price NUMERIC(10, 2),
                    region TEXT,
                    duration TEXT,
                    status TEXT DEFAULT 'pending',
                    smdp_address TEXT,
                    activation_code TEXT,
                    qr_code_file_id TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)
            # 🎯 THE HOT-FIX: Automatically patches your live database
            cur.execute("ALTER TABLE orders ADD COLUMN IF NOT EXISTS price NUMERIC(10, 2);")
            cur.execute("ALTER TABLE orders ADD COLUMN IF NOT EXISTS region TEXT;")
            cur.execute("ALTER TABLE orders ADD COLUMN IF NOT EXISTS duration TEXT;")
            cur.execute("ALTER TABLE orders ADD COLUMN IF NOT EXISTS duration TEXT;")
            cur.execute("ALTER TABLE orders ADD COLUMN IF NOT EXISTS smdp_address TEXT;")
            cur.execute("ALTER TABLE orders ADD COLUMN IF NOT EXISTS activation_code TEXT;")
            cur.execute("ALTER TABLE orders ADD COLUMN IF NOT EXISTS qr_code_file_id TEXT;")

            # 3. Transactions Table (Wallet)
            cur.execute("""
            CREATE TABLE IF NOT EXISTS transactions (
                id SERIAL PRIMARY KEY,
                order_id VARCHAR(50) UNIQUE NOT NULL,
                user_id BIGINT NOT NULL,
                amount NUMERIC(10, 2) NOT NULL,
                coin_amount VARCHAR(50),
                currency VARCHAR(10) NOT NULL,
                status VARCHAR(20) DEFAULT 'pending',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            """)
            cur.execute("ALTER TABLE transactions ADD COLUMN IF NOT EXISTS invoice_url TEXT;")
        conn.commit()
    print("🚀 Database is synced, patched, and tables are ready!")

# --- ADD THIS NEW FUNCTION BELOW init_db() ---

def get_user_orders(user_id, offset=0, limit=5):
    """Fetches a paginated slice of eSIM orders and the total count."""
    with get_connection() as conn:
        with conn.cursor() as cur:
            # Get the specific 5 items
            cur.execute(
                """
                SELECT status, created_at::DATE, region, duration, order_code
                FROM orders
                WHERE user_id = %s
                ORDER BY created_at DESC
                LIMIT %s OFFSET %s
                """,
                (user_id, limit, offset)
            )
            rows = cur.fetchall()
            
            # Get the total number of orders for the pagination math
            cur.execute("SELECT COUNT(*) FROM orders WHERE user_id = %s", (user_id,))
            total = cur.fetchone()[0]
            
            return rows, total
    
    
def get_user_balance(user_id):
    """Fetches user balance, defaulting to 0.0 if not found."""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT balance FROM users WHERE user_id = %s", (user_id,))
            result = cur.fetchone()
            # If result is found, return the first column; otherwise, 0.0
            return float(result[0]) if result and result[0] is not None else 0.0 
    
def add_user(user_id: int, username: str):
    """Saves or updates a user in the Railway database."""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO users (user_id, username)
                VALUES (%s, %s)
                ON CONFLICT (user_id) DO UPDATE SET username = EXCLUDED.username;
            """, (user_id, username))
        conn.commit()    
        
def is_order_id_unique(order_id):
    """Checks the database to ensure an ID hasn't been used yet."""
    # Use 'with' to extract the actual connection from the context manager
    with get_connection() as conn:
        with conn.cursor() as cur:
            # We use str(order_id) to be safe if your DB column is a VARCHAR
            cur.execute("SELECT 1 FROM orders WHERE order_code = %s", (str(order_id),))
            exists = cur.fetchone()
            # If exists is None, the ID is unique (True)
            return exists is None     
        
def create_order_record(order_code, user_id, price, region, duration):
    """Inserts the finalized order with all details into the DB."""
    with get_connection() as conn:
        with conn.cursor() as cur:
            # This order MUST match the SQL command above
            cur.execute(
                """
                INSERT INTO orders (order_code, user_id, price, region, duration, status) 
                VALUES (%s, %s, %s, %s, %s, 'completed')
                """,
                (str(order_code), user_id, price, region, duration)
            )
        conn.commit()

def deduct_user_balance(user_id, amount):
    """Subtracts the cost from the user's balance."""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE users SET balance = balance - %s WHERE user_id = %s",
                (amount, user_id)
            )
        conn.commit()        
        
        
def log_new_transaction(order_id, user_id, amount, coin_amount, currency,invoice_url):
    """Saves a new pending transaction to the ledger."""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO transactions (order_id, user_id, amount, coin_amount, currency, status,invoice_url)
                VALUES (%s, %s, %s, %s, %s, 'pending', %s)
                """,
                (str(order_id), user_id, amount, str(coin_amount), currency,invoice_url)
            )
        conn.commit()

def get_transaction_history(user_id, limit=5):
    """Fetches the last X transactions for the wallet view."""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT created_at::DATE, order_id, status, amount 
                FROM transactions 
                WHERE user_id = %s 
                ORDER BY created_at DESC 
                LIMIT %s
                """,
                (user_id, limit)
            )
            return cur.fetchall()      
        
def cancel_transaction(order_id):
    """Marks a specific order as canceled in the ledger."""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE transactions SET status = 'canceled' WHERE order_id = %s",
                (str(order_id),)
            )
        conn.commit()          
        

def complete_deposit(order_id):
    """
    Updates the database and returns data for the Telegram notification.
    Uses psycopg (PostgreSQL) with context managers for safety.
    """
    try:
        # 1. Open Connection (Automatic close)
        with psycopg.connect(DB_URL, row_factory=dict_row) as conn:
            # 2. Open Cursor (Automatic close)
            with conn.cursor() as cur:
                
                # Fetch transaction details
                cur.execute(
                    "SELECT user_id, amount, status FROM transactions WHERE order_id = %s",
                    (str(order_id),)
                )
                row = cur.fetchone()

                # Guardrail: Check if order exists or is already done
                if not row:
                    print(f"❌ Order {order_id} not found.")
                    return None
                
                if row['status'] == 'completed':
                    print(f"⚠️ Order {order_id} already processed.")
                    return None

                # 3. Perform the Updates
                # Add money to user's balance
                cur.execute(
                    "UPDATE users SET balance = balance + %s WHERE user_id = %s",
                    (row['amount'], row['user_id'])
                )
                
                # Mark the transaction as completed
                cur.execute(
                    "UPDATE transactions SET status = 'completed' WHERE order_id = %s",
                    (str(order_id),)
                )
                
                # Psycopg 3 commits automatically when leaving the 'with' block 
                # if no errors occurred.
                print(f"💰 SUCCESS: ${row['amount']} added to User {row['user_id']}")
                return row['user_id'], row['amount']

    except Exception as e:
        print(f"🔥 Database Error: {e}")
        return None       
    
    
def check_and_get_pending_order(user_id):
    """
    1. Auto-expires anything older than 59 mins.
    2. Returns any active pending order with the exact seconds remaining.
    """
    with get_connection() as conn:
        with conn.cursor() as cur:
            # 1. THE AUTO-CLEANUP (Updates DB before checking)
            cur.execute("""
                UPDATE orders SET status = 'expired' 
                WHERE user_id = %s AND status = 'pending' AND created_at < NOW() - INTERVAL '59 minutes';
            """, (user_id,))
            
            cur.execute("""
                UPDATE transactions SET status = 'expired' 
                WHERE user_id = %s AND status = 'pending' AND created_at < NOW() - INTERVAL '59 minutes';
            """, (user_id,))
            conn.commit()

            # 2. CHECK eSIM ORDERS
            cur.execute("""
                SELECT 'esim' as type, order_code as id, price as amount, 
                       EXTRACT(EPOCH FROM (created_at + INTERVAL '59 minutes' - NOW())) as sec_left 
                FROM orders WHERE user_id = %s AND status = 'pending'
            """, (user_id,))
            esim_pending = cur.fetchone()
            if esim_pending: return esim_pending

            # 3. CHECK WALLET TOP-UPS
            cur.execute("""
                SELECT 'wallet' as type, order_id as id, amount, 
                       EXTRACT(EPOCH FROM (created_at + INTERVAL '59 minutes' - NOW())) as sec_left 
                FROM transactions WHERE user_id = %s AND status = 'pending'
            """, (user_id,))
            wallet_pending = cur.fetchone()
            
            return wallet_pending

def force_cancel_order(order_id, order_type):
    """Triggered when user clicks 'Cancel & Start New'."""
    with get_connection() as conn:
        with conn.cursor() as cur:
            if order_type == 'esim':
                cur.execute("UPDATE orders SET status = 'canceled' WHERE order_code = %s", (str(order_id),))
            else:
                cur.execute("UPDATE transactions SET status = 'canceled' WHERE order_id = %s", (str(order_id),))
        conn.commit()  
        
def get_order_by_code(order_code):
    """Fetches the core details of an order to build the Admin Topic summary."""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT user_id, price, region, duration, status FROM orders WHERE order_code = %s",
                (str(order_code),)
            )
            return cur.fetchone()

def save_delivery_details(order_code, smdp, activation, qr_id):
    """Saves the eSIM data from the Wizard and officially marks it as delivered."""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE orders 
                SET smdp_address = %s, 
                    activation_code = %s, 
                    qr_code_file_id = %s, 
                    status = 'delivered'
                WHERE order_code = %s
                """,
                (smdp, activation, qr_id, str(order_code))
            )
        conn.commit()

def get_delivery_details(order_code):
    """Pulls the saved eSIM data when you click 'Edit & Resend'."""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT smdp_address, activation_code, qr_code_file_id FROM orders WHERE order_code = %s",
                (str(order_code),)
            )
            return cur.fetchone()          
        
def close_db():
    """Closes the connection pool gracefully."""
    if db_pool:
        db_pool.close()
        print("🔌 Database connection pool closed.")        