#!/usr/bin/env python3
import time
import os
import mysql.connector
from mysql.connector import Error

host = os.getenv("DB_HOST", "db")
port = int(os.getenv("DB_PORT", "3306"))
user = os.getenv("DB_USER")
password = os.getenv("DB_PASSWORD")
database = os.getenv("DB_NAME")

timeout = 60  # seconds
start_time = time.time()

print(f"⏳ Waiting for DB at {host}:{port} to be ready...")

while True:
    try:
        conn = mysql.connector.connect(
            host=host,
            port=port,
            user=user,
            password=password,
            database=database
        )
        if conn.is_connected():
            print("✅ Database is ready!")
            conn.close()
            break
    except Error as e:
        print(f"🛑 DB not ready yet: {e}")
    time.sleep(2)
    if time.time() - start_time > timeout:
        print("❌ Timeout waiting for the database.")
        exit(1)
