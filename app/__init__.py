import os
import sqlite3
from flask import Flask
from apscheduler.schedulers.background import BackgroundScheduler
from .collectors.main_collector import fetch_and_store_jobs
# We will create this scholarship collector next
from .collectors.scholarship_collector import fetch_scholarships
from .email_service import send_email_alerts

def get_db_connection():
    conn = sqlite3.connect('app/database/remote_bot.db')
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    os.makedirs('app/database', exist_ok=True)
    conn = get_db_connection()
    
    # 1. Jobs Table
    conn.execute('''
        CREATE TABLE IF NOT EXISTS opportunities (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT, company TEXT, opportunity_type TEXT, skill_category TEXT,
            remote_status TEXT, description TEXT, apply_url TEXT UNIQUE,
            source TEXT, posted_date TEXT, score INTEGER DEFAULT 0,
            is_sent INTEGER DEFAULT 0, is_saved INTEGER DEFAULT 0
        )
    ''')
    
    # 2. NEW: Scholarships Table
    conn.execute('''
        CREATE TABLE IF NOT EXISTS scholarships (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT,
            provider TEXT,
            level TEXT,
            description TEXT,
            apply_url TEXT UNIQUE,
            source TEXT,
            posted_date TEXT
        )
    ''')
    conn.commit()
    conn.close()

def automated_job_run():
    print("Running scheduled fetches...")
    fetch_and_store_jobs()
    fetch_scholarships()
    send_email_alerts()

def create_app():
    app = Flask(__name__)
    init_db()

    scheduler = BackgroundScheduler()
    scheduler.add_job(func=automated_job_run, trigger="interval", hours=6)
    scheduler.start()

    from .routes import main_bp
    app.register_blueprint(main_bp)

    return app
