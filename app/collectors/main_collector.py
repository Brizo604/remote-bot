import requests
import sqlite3
import json
import feedparser
import os
import difflib
from datetime import datetime, timedelta

DB_PATH = 'app/database/remote_bot.db'
STATUS_PATH = 'app/database/status.json'

def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

# --- THE GATEKEEPER FILTER ---
def categorize_target_job(title):
    """
    Strict filter with a BLACKLIST. Returns the category if it matches,
    or None if it fails.
    """
    t = title.lower()

    # --- 1. THE STRICT BLACKLIST ---
    # If any of these words are in the title, INSTANTLY reject the job.
    bad_words = ['sales', 'b2b', 'b2c', 'outbound', 'cold calling', 'lead gen', 'business development', 'bdc', 'ae', 'account executive']
    if any(bad_word in t for bad_word in bad_words):
        return None

    # --- 2. THE WHITELIST ---
    # Cybersecurity & Ethical Hacking
    if any(kw in t for kw in ['cyber', 'security', 'ethical hacker', 'penetration', 'infosec', 'soc', 'vulnerability']):
        return 'Cybersecurity'

    # Junior Tech Roles
    is_junior = any(kw in t for kw in ['junior', 'jr', 'entry', 'intern'])
    is_tech = any(kw in t for kw in ['developer', 'software', 'computer science', 'automation', 'web', 'engineer'])
    if is_junior and is_tech:
        return 'Junior Tech'

    # Virtual Assistant & Administration
    if 'virtual assistant' in t or 'va' in t.split():
        return 'Virtual Assistant'
    if 'admin' in t or 'data entry' in t or 'clerk' in t:
        return 'Administration'

    # IT Support
    if any(kw in t for kw in ['it support', 'helpdesk', 'help desk', 'technical support', 'desktop support']):
        return 'IT Support'

    # Customer Care
    if any(kw in t for kw in ['customer care', 'customer service', 'customer support', 'client success']):
        return 'Customer Care'

    # Social Media & Account Management
    if 'social media' in t:
        return 'Social Media'
    
    # Adjusted to avoid "Sales Account Manager"
    if 'account manag' in t or 'key account' in t:
        return 'Account Management'

    # If it doesn't match the whitelist, reject it
    return None

def fetch_and_store_jobs():
    print("Starting strictly filtered job fetch...")
    all_jobs = []
    
    # --- Category 1: Free JSON APIs (Unfiltered endpoints, filtered locally) ---
    all_jobs.extend(fetch_api_remotive())
    all_jobs.extend(fetch_api_arbeitnow())
    all_jobs.extend(fetch_api_jobicy())
    
    # --- Category 2: Free RSS Feeds (Targeted endpoints) ---
    rss_feeds = [
        ("https://weworkremotely.com/categories/remote-customer-support-jobs.rss", "We Work Remotely"),
        ("https://weworkremotely.com/categories/remote-system-administration-jobs.rss", "We Work Remotely"),
        ("https://weworkremotely.com/categories/remote-programming-jobs.rss", "We Work Remotely"),
        ("https://www.workingnomads.com/jobsfeed", "Working Nomads"),
        ("https://dailyremote.com/remote-jobs.rss", "DailyRemote"),
        ("https://www.upwork.com/ab/feed/jobs/rss?q=remote+virtual+assistant", "Upwork"),
        ("https://www.upwork.com/ab/feed/jobs/rss?q=remote+cybersecurity", "Upwork"),
        ("https://www.upwork.com/ab/feed/jobs/rss?q=remote+junior+developer", "Upwork"),
        ("https://www.upwork.com/ab/feed/jobs/rss?q=remote+it+support", "Upwork"),
        ("https://remoteok.com/remote-jobs.rss", "RemoteOK")
    ]
    
    for feed_url, source_name in rss_feeds:
        all_jobs.extend(fetch_rss_feed(feed_url, source_name))
    
    save_to_db(all_jobs)
    update_status()
    print("Filtered job fetch complete!")

def fetch_api_remotive():
    jobs = []
    try:
        data = requests.get("https://remotive.com/api/remote-jobs", timeout=10).json()
        for job in data.get('jobs', [])[:50]:
            formatted = format_job(job.get('title'), job.get('company_name'), job.get('description'), job.get('url'), 'Remotive API', job.get('publication_date')[:10])
            if formatted: jobs.append(formatted)
    except: pass
    return jobs

def fetch_api_arbeitnow():
    jobs = []
    try:
        data = requests.get("https://www.arbeitnow.com/api/job-board-api", timeout=10).json()
        for job in data.get('data', [])[:50]:
            if job.get('remote'):
                formatted = format_job(job.get('title'), job.get('company_name'), job.get('description'), job.get('url'), 'Arbeitnow API', datetime.fromtimestamp(job.get('created_at')).strftime("%Y-%m-%d"))
                if formatted: jobs.append(formatted)
    except: pass
    return jobs

def fetch_api_jobicy():
    jobs = []
    try:
        data = requests.get("https://jobicy.com/api/v2/remote-jobs?count=50", timeout=10).json()
        for job in data.get('jobs', []):
            formatted = format_job(job.get('jobTitle'), job.get('companyName'), job.get('jobDescription'), job.get('url'), 'Jobicy API', job.get('pubDate')[:10])
            if formatted: jobs.append(formatted)
    except: pass
    return jobs

def fetch_rss_feed(url, source):
    jobs = []
    try:
        feed = feedparser.parse(url)
        for entry in feed.entries[:30]:
            title_parts = entry.title.split(': ')
            company = title_parts[0] if len(title_parts) > 1 else 'Unknown'
            title = title_parts[-1]
            try:
                dt = datetime.strptime(entry.published[5:16], "%d %b %Y")
                posted_date = dt.strftime("%Y-%m-%d")
            except:
                posted_date = datetime.now().strftime("%Y-%m-%d")

            formatted = format_job(title, company, entry.description, entry.link, source, posted_date)
            if formatted: jobs.append(formatted)
    except: pass
    return jobs

def format_job(title, company, desc, url, source, date_str):
    category = categorize_target_job(title)
    if not category:
        return None # Drop the job if it doesn't match your criteria

    return {
        'title': str(title)[:100],
        'company': str(company)[:100],
        'opportunity_type': 'Full-time',
        'skill_category': category,
        'remote_status': 'Remote',
        'description': str(desc)[:500] + '...',
        'apply_url': str(url),
        'source': source,
        'posted_date': date_str
    }

# --- THE SMART DEDUPLICATION ENGINE ---
def is_similar(string1, string2):
    if not string1 or not string2: return False
    ratio = difflib.SequenceMatcher(None, string1.lower(), string2.lower()).ratio()
    return ratio > 0.85

def save_to_db(jobs):
    conn = get_db_connection()
    cursor = conn.cursor()
    twenty_one_days_ago = datetime.now() - timedelta(days=21)
    
    cursor.execute("SELECT title, company FROM opportunities WHERE posted_date >= ?", (twenty_one_days_ago.strftime("%Y-%m-%d"),))
    existing_jobs = cursor.fetchall()
    
    saved_count = 0
    duplicates_caught = 0
    
    for job in jobs:
        try:
            posted_date = datetime.strptime(job['posted_date'], "%Y-%m-%d")
            if posted_date < twenty_one_days_ago: continue
                
            is_clone = False
            for ex_job in existing_jobs:
                if job['company'].lower() == ex_job['company'].lower():
                    if is_similar(job['title'], ex_job['title']):
                        is_clone = True
                        break
            
            if is_clone:
                duplicates_caught += 1
                continue
                
            cursor.execute('''
                INSERT INTO opportunities (
                    title, company, opportunity_type, skill_category, 
                    remote_status, description, apply_url, source, posted_date
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                job['title'], job['company'], job['opportunity_type'], 
                job['skill_category'], job['remote_status'], job['description'], 
                job['apply_url'], job['source'], job['posted_date']
            ))
            
            existing_jobs.append({'title': job['title'], 'company': job['company']})
            saved_count += 1
            
        except sqlite3.IntegrityError:
            continue
        except Exception:
            pass 

    conn.commit()
    conn.close()
    print(f"Saved {saved_count} highly targeted jobs. Blocked {duplicates_caught} duplicates.")

def update_status():
    os.makedirs('app/database', exist_ok=True)
    status = {"last_fetch": datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
    with open(STATUS_PATH, 'w') as f:
        json.dump(status, f)
