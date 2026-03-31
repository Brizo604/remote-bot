import sqlite3
import feedparser
from datetime import datetime

DB_PATH = 'app/database/remote_bot.db'

def get_db_connection():
    return sqlite3.connect(DB_PATH)

def fetch_scholarships():
    print("Starting scholarship fetch...")
    all_scholarships = []
    
    rss_feeds = [
        ("https://www.opportunitiesforafricans.com/feed/", "Opportunities for Africans"),
        ("https://www.youthop.com/feed", "Youth Opportunities"),
        ("https://scholarship-positions.com/feed/", "Scholarship Positions")
    ]
    
    for url, source in rss_feeds:
        try:
            feed = feedparser.parse(url)
            for entry in feed.entries[:15]:
                # Safe date parsing
                try:
                    dt = datetime.strptime(entry.published[5:16], "%d %b %Y")
                    posted_date = dt.strftime("%Y-%m-%d")
                except:
                    posted_date = datetime.now().strftime("%Y-%m-%d")

                all_scholarships.append({
                    'title': entry.title[:150],
                    'provider': 'Various / See Link',
                    'level': 'Undergrad/Masters/PhD', 
                    'description': entry.description[:400] + '...',
                    'apply_url': entry.link,
                    'source': source,
                    'posted_date': posted_date
                })
        except Exception as e:
            print(f"Error fetching {source}: {e}")
            
    save_scholarships_to_db(all_scholarships)

def save_scholarships_to_db(scholarships):
    conn = get_db_connection()
    cursor = conn.cursor()
    saved_count = 0
    
    for item in scholarships:
        try:
            cursor.execute('''
                INSERT INTO scholarships (
                    title, provider, level, description, apply_url, source, posted_date
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (
                item['title'], item['provider'], item['level'], 
                item['description'], item['apply_url'], item['source'], item['posted_date']
            ))
            saved_count += 1
        except sqlite3.IntegrityError:
            continue # Skip duplicates
            
    conn.commit()
    conn.close()
    print(f"Saved {saved_count} new scholarships to the database.")
