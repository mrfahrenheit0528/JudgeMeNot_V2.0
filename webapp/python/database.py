import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Fallback to local sqlite for testing if no MySQL connection variables exposed
db_username = os.getenv("db_username", "root")
db_pass = os.getenv("db_pass", "")
db_host = os.getenv("db_host", "localhost")
db_name = "judgemenot_v2_db"

# Currently resolving to SQLite for ease of testing during development
# In production, replace the engine below with standard mysql strings
DATABASE_URL = "sqlite:///judgemenot_v2.db"

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
