import PyPDF2
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

def extract_text_from_pdf(pdf_file):
    try:
        reader = PyPDF2.PdfReader(pdf_file)
        text = ""
        for page in reader.pages:
            text += page.extract_text() + " "
        return text
    except Exception as e:
        print(f"Error reading PDF: {e}")
        return ""

def rank_jobs(cv_text, jobs):
    if not cv_text or not jobs:
        # If no CV, return jobs as regular dictionaries with 0 score
        return [dict(job) | {'score': 0, 'reasons': []} for job in jobs]
    
    # 1. Prepare texts for AI matching
    # We combine the title, category, and description of the job
    job_texts = [f"{job['title']} {job['skill_category']} {job['description']}" for job in jobs]
    
    # The CV is the first document, followed by all jobs
    documents = [cv_text] + job_texts
    
    # 2. Calculate TF-IDF Cosine Similarity
    vectorizer = TfidfVectorizer(stop_words='english')
    tfidf_matrix = vectorizer.fit_transform(documents)
    
    # Compare CV (index 0) against all jobs (index 1 to end)
    similarities = cosine_similarity(tfidf_matrix[0:1], tfidf_matrix[1:]).flatten()
    
    ranked_jobs = []
    for i, job in enumerate(jobs):
        job_dict = dict(job)
        reasons = []
        
        # Base AI Match Score (Converted to percentage)
        ai_score = int(similarities[i] * 100)
        score = ai_score
        
        if ai_score > 10:
            reasons.append(f"AI Keyword Match: {ai_score}%")
            
        # 3. Rule-based Scoring [cite: 60-63]
        desc_lower = job_dict['description'].lower()
        title_lower = job_dict['title'].lower()
        
        # Remote Confirmation
        if 'remote' in desc_lower or 'remote' in title_lower:
            score += 10
            reasons.append("Remote Confirmed (+10)")
            
        # Junior/Intern Preference
        if 'junior' in title_lower or 'intern' in title_lower or 'entry' in title_lower:
            score += 15
            reasons.append("Junior/Entry Level (+15)")
            
        job_dict['score'] = min(score, 100) # Cap at 100 maximum
        job_dict['reasons'] = reasons
        ranked_jobs.append(job_dict)
        
    # Sort the jobs from highest score to lowest
    ranked_jobs.sort(key=lambda x: x['score'], reverse=True)
    return ranked_jobs
