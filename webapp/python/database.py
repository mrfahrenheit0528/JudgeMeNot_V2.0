import os
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

load_dotenv()
from sqlalchemy.orm import sessionmaker

# XAMPP Default MySQL Connection variables
db_username = os.getenv("db_username", "root")
db_pass = os.getenv("db_pass", "")
db_host = os.getenv("db_host", "localhost")
db_name = "judgemenot_v2_db"

# Create Database if it doesn't exist (for XAMPP out of the box experience)
try:
    import pymysql
    server_url = f"mysql+pymysql://{db_username}:{db_pass}@{db_host}/" if db_pass else f"mysql+pymysql://{db_username}@{db_host}/"
    server_engine = create_engine(server_url)
    with server_engine.connect() as conn:
        conn.execute(text(f"CREATE DATABASE IF NOT EXISTS {db_name}"))
except Exception as e:
    print(f"Warning: Could not auto-create database. Please ensure XAMPP MySQL is running. {e}")

# Main Application DB Engine
DATABASE_URL = f"mysql+pymysql://{db_username}:{db_pass}@{db_host}/{db_name}" if db_pass else f"mysql+pymysql://{db_username}@{db_host}/{db_name}"

engine = create_engine(DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
