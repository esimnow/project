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
            # 1. Create table if it doesn't exist
            cur.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    user_id BIGINT PRIMARY KEY,
                    username TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)

            # 2. THE FIX: Add the balance column to the existing table
            # This line is safe to run even if the column already exists
            cur.execute("""
                ALTER TABLE users ADD COLUMN IF NOT EXISTS balance DECIMAL(10, 2) DEFAULT 0.0;
            """)

            # 3. Create orders table
            cur.execute("""
                CREATE TABLE IF NOT EXISTS orders (
                    id SERIAL PRIMARY KEY,
                    user_id BIGINT REFERENCES users(user_id),
                    order_code TEXT UNIQUE,
                    description TEXT,
                    status TEXT DEFAULT 'pending',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)

            cur.execute("""
            CREATE TABLE IF NOT EXISTS transactions (
                id SERIAL PRIMARY KEY,
                order_id VARCHAR(50) UNIQUE NOT NULL,
                user_id BIGINT NOT NULL,
                amount NUMERIC(10, 2) NOT NULL,
                coin_amount VARCHAR(50),
                currency VARCHAR(10) NOT NULL,
                status VARCHAR(20) DEFAULT 'pending', -- pending, completed, expired, canceled
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """)
        conn.commit()
    print("🚀 Database is synced and tables are ready!")
    
    
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
        
        
def log_new_transaction(order_id, user_id, amount, coin_amount, currency):
    """Saves a new pending transaction to the ledger."""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO transactions (order_id, user_id, amount, coin_amount, currency, status)
                VALUES (%s, %s, %s, %s, %s, 'pending')
                """,
                (str(order_id), user_id, amount, str(coin_amount), currency)
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
        
def close_db():
    """Closes the connection pool gracefully."""
    if db_pool:
        db_pool.close()
        print("🔌 Database connection pool closed.")        