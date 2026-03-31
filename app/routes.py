from flask import Blueprint, render_template, redirect, url_for, request
import sqlite3
import json
import os
from datetime import datetime, timedelta
from .collectors.main_collector import fetch_and_store_jobs
from .collectors.scholarship_collector import fetch_scholarships
from .email_service import send_email_alerts
from .filters.ranker import extract_text_from_pdf, rank_jobs # NEW IMPORT

main_bp = Blueprint('main', __name__)

def get_db_connection():
    conn = sqlite3.connect('app/database/remote_bot.db')
    conn.row_factory = sqlite3.Row
    return conn

# --- JOB DASHBOARD & AI MATCHER ---
# Added methods to accept POST requests for file uploads
@main_bp.route('/', methods=['GET', 'POST'])
def index():
    conn = get_db_connection()
    search = request.args.get('search', '')
    category = request.args.get('category', 'all')
    
    query = 'SELECT * FROM opportunities WHERE 1=1'
    params = []
    
    if search:
        query += ' AND (title LIKE ? OR company LIKE ? OR description LIKE ?)'
        search_term = f'%{search}%'
        params.extend([search_term, search_term, search_term])
        
    if category != 'all':
        query += ' AND skill_category = ?'
        params.append(category)
        
    query += ' ORDER BY posted_date DESC LIMIT 100'
    raw_jobs = conn.execute(query, params).fetchall()
    
    categories = conn.execute('SELECT DISTINCT skill_category FROM opportunities').fetchall()
    conn.close()

    # --- AI CV MATCHING LOGIC ---
    cv_text = ""
    if request.method == 'POST' and 'cv_file' in request.files:
        file = request.files['cv_file']
        if file.filename.endswith('.pdf'):
            cv_text = extract_text_from_pdf(file)
            
    # Pass jobs through the ranker (will sort by date if no CV, or by score if CV uploaded)
    ranked_jobs = rank_jobs(cv_text, raw_jobs)
    
    last_fetch = "Never"
    if os.path.exists('app/database/status.json'):
        with open('app/database/status.json', 'r') as f:
            status = json.load(f)
            last_fetch = status.get('last_fetch', 'Never')

    return render_template('index.html', jobs=ranked_jobs, last_fetch=last_fetch, 
                           categories=categories, current_search=search, current_category=category,
                           ai_active=bool(cv_text))

@main_bp.route('/run-fetch')
def run_fetch():
    fetch_and_store_jobs()
    return redirect(url_for('main.index'))

@main_bp.route('/send-email')
def send_email():
    send_email_alerts()
    return redirect(url_for('main.index'))

@main_bp.route('/clear-old')
def clear_old():
    conn = get_db_connection()
    cutoff = (datetime.now() - timedelta(days=21)).strftime("%Y-%m-%d")
    conn.execute('DELETE FROM opportunities WHERE posted_date < ? AND is_saved = 0', (cutoff,))
    conn.commit()
    conn.close()
    return redirect(url_for('main.index'))

@main_bp.route('/toggle-save/<int:job_id>')
def toggle_save(job_id):
    conn = get_db_connection()
    job = conn.execute('SELECT is_saved FROM opportunities WHERE id = ?', (job_id,)).fetchone()
    if job:
        new_status = 0 if job['is_saved'] == 1 else 1
        conn.execute('UPDATE opportunities SET is_saved = ? WHERE id = ?', (new_status, job_id))
        conn.commit()
    conn.close()
    return redirect(request.referrer or url_for('main.index'))

@main_bp.route('/saved')
def saved_jobs():
    conn = get_db_connection()
    jobs = conn.execute('SELECT * FROM opportunities WHERE is_saved = 1 ORDER BY posted_date DESC').fetchall()
    conn.close()
    return render_template('saved.html', jobs=jobs)

@main_bp.route('/scholarships')
def scholarships_page():
    conn = get_db_connection()
    items = conn.execute('SELECT * FROM scholarships ORDER BY posted_date DESC LIMIT 50').fetchall()
    conn.close()
    return render_template('scholarships.html', scholarships=items)

@main_bp.route('/run-scholarship-fetch')
def run_scholarship_fetch():
    fetch_scholarships()
    return redirect(url_for('main.scholarships_page'))
# --- ANALYTICS ROUTE ---
@main_bp.route('/analytics')
def analytics_page():
    conn = get_db_connection()
    
    # 1. Total Jobs
    total_jobs = conn.execute('SELECT COUNT(*) FROM opportunities').fetchone()[0]
    
    # 2. Category Breakdown
    categories_raw = conn.execute('SELECT skill_category, COUNT(*) as count FROM opportunities GROUP BY skill_category').fetchall()
    category_labels = [row['skill_category'] for row in categories_raw]
    category_counts = [row['count'] for row in categories_raw]
    
    # 3. Trend: Jobs per Day (Last 7 days)
    seven_days_ago = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")
    trends_raw = conn.execute('SELECT posted_date, COUNT(*) as count FROM opportunities WHERE posted_date >= ? GROUP BY posted_date ORDER BY posted_date', (seven_days_ago,)).fetchall()
    trend_labels = [row['posted_date'] for row in trends_raw]
    trend_counts = [row['count'] for row in trends_raw]
    
    # 4. Total Scholarships
    total_scholarships = conn.execute('SELECT COUNT(*) FROM scholarships').fetchone()[0]
    
    conn.close()
    
    return render_template('analytics.html', 
                           total_jobs=total_jobs, 
                           total_scholarships=total_scholarships,
                           category_labels=json.dumps(category_labels), 
                           category_counts=json.dumps(category_counts),
                           trend_labels=json.dumps(trend_labels),
                           trend_counts=json.dumps(trend_counts))
