import smtplib
import sqlite3
import os
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from dotenv import load_dotenv

# Load the credentials from your .env file
load_dotenv()

def send_email_alerts():
    sender = os.getenv('EMAIL_ADDRESS')
    password = os.getenv('EMAIL_APP_PASSWORD')
    receiver = os.getenv('EMAIL_RECEIVER')

    if not sender or not password:
        print("Email credentials missing in .env file.")
        return

    conn = sqlite3.connect('app/database/remote_bot.db')
    cursor = conn.cursor()
    
    # Grab only jobs that haven't been sent yet [cite: 83]
    cursor.execute("SELECT id, title, company, apply_url FROM opportunities WHERE is_sent = 0")
    new_jobs = cursor.fetchall()

    if not new_jobs:
        print("No new jobs to send.")
        conn.close()
        return

    # Build the email
    msg = MIMEMultipart()
    msg['From'] = sender
    msg['To'] = receiver
    msg['Subject'] = f"Remote Bot: {len(new_jobs)} New Jobs Found!"

    body = "Here are your new remote opportunities:\n\n"
    for job in new_jobs:
        body += f"- {job[1]} at {job[2]}\n  Apply: {job[3]}\n\n"

    msg.attach(MIMEText(body, 'plain'))

    try:
        # Connect to Gmail and send [cite: 78]
        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        server.login(sender, password)
        server.send_message(msg)
        server.quit()
        
        # Mark all these jobs as sent so you don't get duplicates [cite: 84]
        for job in new_jobs:
            cursor.execute("UPDATE opportunities SET is_sent = 1 WHERE id = ?", (job[0],))
        conn.commit()
        print(f"Successfully sent {len(new_jobs)} jobs via email!")
    except Exception as e:
        print(f"Failed to send email: {e}")
        
    conn.close()
