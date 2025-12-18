
import psycopg2
import config

def check_data():
    try:
        print(f"Connecting to {config.DB_HOST}...")
        conn = psycopg2.connect(
            host=config.DB_HOST,
            port=config.DB_PORT,
            database=config.DB_NAME,
            user=config.DB_USER,
            password=config.DB_PASSWORD
        )
        print("✅ Connected!")
        
        with conn.cursor() as cur:
            cur.execute("SELECT count(*) FROM trade_logs;")
            count = cur.fetchone()[0]
            print(f"📊 Total Rows in trade_logs: {count}")
            
            if count > 0:
                cur.execute("SELECT * FROM trade_logs ORDER BY id DESC LIMIT 1;")
                print("Latest Row:", cur.fetchone())
                
    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    check_data()
