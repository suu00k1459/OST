
import psycopg2
import os

DB_HOST = "timescaledb"
DB_PORT = 5432
DB_NAME = "flead"
DB_USER = "flead"
DB_PASSWORD = "password"

try:
    conn = psycopg2.connect(
        host=DB_HOST,
        port=DB_PORT,
        database=DB_NAME,
        user=DB_USER,
        password=DB_PASSWORD
    )
    conn.autocommit = True
    cur = conn.cursor()
    
    print("Dropping old dashboard_metrics table...")
    cur.execute("DROP TABLE IF EXISTS dashboard_metrics CASCADE;")
    print("✓ Table dropped.")
    
    conn.close()
except Exception as e:
    print(f"Error: {e}")
