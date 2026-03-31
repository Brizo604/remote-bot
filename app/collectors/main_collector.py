import requests
import sqlite3
import json
import feedparser
import os
import time
from bs4 import BeautifulSoup
from datetime import datetime

DB_PATH = 'app/database/remote_bot.db'
STATUS_PATH = 'app/database/status.json'

def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

# --- THE GATEKEEPER FILTER ---
def categorize_target_job(title):
    t = title.lower()
    # 1. BLACKLIST: Instant rejection for sales/marketing
    bad_words = ['sales', 'b2b', 'b2c', 'outbound', 'cold calling', 'lead gen', 'business development', 'ae', 'account executive']
    if any(bw in t for bw in bad_words): return None

    # 2. WHITELIST: Brizo Labs Niches
    if any(kw in t for kw in ['virtual assistant', 'personal assistant', 'executive assistant', 'admin assistant']):
        return 'Virtual Assistant'
    if 'va' in t.split():
        return 'Virtual Assistant'
    if any(kw in t for kw in ['cyber', 'security', 'ethical hacker', 'penetration', 'infosec', 'soc', 'vulnerability']):
        return 'Cybersecurity'
    if any(kw in t for kw in ['junior', 'jr', 'entry', 'intern']) and any(kw in t for kw in ['developer', 'software', 'automation', 'web', 'engineer']):
        return 'Junior Tech'
    if any(kw in t for kw in ['it support', 'helpdesk', 'technical support']):
        return 'IT Support'
    if any(kw in t for kw in ['customer care', 'customer service', 'support']):
        return 'Customer Care'
    return None

# --- SOURCES ---
def fetch_linkedin_jobs(keywords):
    print(f"Scouting LinkedIn for {keywords}...")
    jobs = []
    url = f"https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search?keywords={keywords}&location=Remote&start=0"
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    try:
        res = requests.get(url, headers=headers, timeout=15)
        soup = BeautifulSoup(res.text, 'html.parser')
        for post in soup.find_all('li'):
            title_node = post.find('h3', class_='base-search-card__title')
            company_node = post.find('h4', class_='base-search-card__subtitle')
            link_node = post.find('a', class_='base-card__full-link')
            if title_node and company_node and link_node:
                formatted = format_job(title_node.get_text(strip=True), company_node.get_text(strip=True), "LinkedIn Opportunity", link_node['href'], "LinkedIn", datetime.now().strftime("%Y-%m-%d"))
                if formatted: jobs.append(formatted)
        time.sleep(3) # Avoid IP block
    except: pass
    return jobs

def fetch_api_remotive():
    jobs = []
    try:
        data = requests.get("https://remotive.com/api/remote-jobs", timeout=10).json()
        for job in data.get('jobs', [])[:40]:
            formatted = format_job(job.get('title'), job.get('company_name'), job.get('description'), job.get('url'), 'Remotive API', job.get('publication_date')[:10])
            if formatted: jobs.append(formatted)
    except: pass
    return jobs

def fetch_api_jobicy():
    jobs = []
    try:
        data = requests.get("https://jobicy.com/api/v2/remote-jobs?count=40", timeout=10).json()
        for job in data.get('jobs', []):
            formatted = format_job(job.get('jobTitle'), job.get('companyName'), job.get('jobDescription'), job.get('url'), 'Jobicy API', job.get('pubDate')[:10])
            if formatted: jobs.append(formatted)
    except: pass
    return jobs

def fetch_rss_feed(url, source):
    jobs = []
    try:
        feed = feedparser.parse(url)
        for entry in feed.entries[:20]:
            title_parts = entry.title.split(': ')
            company = title_parts[0] if len(title_parts) > 1 else 'Unknown'
            title = title_parts[-1]
            formatted = format_job(title, company, entry.description, entry.link, source, datetime.now().strftime("%Y-%m-%d"))
            if formatted: jobs.append(formatted)
    except: pass
    return jobs

def format_job(title, company, desc, url, source, date_str):
    category = categorize_target_job(title)
    if not category: return None
    return {
        'title': str(title)[:100], 'company': str(company)[:100], 'opportunity_type': 'Full-time',
        'skill_category': category, 'remote_status': 'Remote', 'description': str(desc)[:400] + '...',
        'apply_url': str(url), 'source': source, 'posted_date': date_str
    }

def save_to_db(jobs):
    conn = get_db_connection()
    cursor = conn.cursor()
    saved = 0
    for job in jobs:
        try:
            cursor.execute('''INSERT INTO opportunities (title, company, opportunity_type, skill_category, remote_status, description, apply_url, source, posted_date)
                              VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)''', 
                           (job['title'], job['company'], job['opportunity_type'], job['skill_category'], job['remote_status'], job['description'], job['apply_url'], job['source'], job['posted_date']))
            saved += 1
        except: continue
    conn.commit()
    conn.close()
    print(f"Success: {saved} new jobs added.")

def update_status():
    status = {"last_fetch": datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
    os.makedirs('app/database', exist_ok=True)
    with open(STATUS_PATH, 'w') as f: json.dump(status, f)

def fetch_and_store_jobs():
    all_jobs = []
    all_jobs.extend(fetch_api_remotive())
    all_jobs.extend(fetch_api_jobicy())
    all_jobs.extend(fetch_linkedin_jobs("Cybersecurity"))
    all_jobs.extend(fetch_linkedin_jobs("Virtual Assistant"))
    all_jobs.extend(fetch_linkedin_jobs("IT Support"))
    
    rss_feeds = [
        ("https://weworkremotely.com/categories/remote-customer-support-jobs.rss", "WWR"),
        ("https://weworkremotely.com/categories/remote-system-administration-jobs.rss", "WWR"),
        ("https://www.upwork.com/ab/feed/jobs/rss?q=virtual+assistant", "Upwork VA"),
        ("https://www.upwork.com/ab/feed/jobs/rss?q=cybersecurity", "Upwork Cyber")
    ]
    for url, src in rss_feeds:
        all_jobs.extend(fetch_rss_feed(url, src))
    
    save_to_db(all_jobs)
    update_status()
