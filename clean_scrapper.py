import numbers
import os
import google.generativeai as genai
import requests
import pandas as pd
import json
import time
import re
from dotenv import load_dotenv

load_dotenv()

# Configure Gemini + Serper
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
SERPER_API_KEY = os.getenv("SERPER_API_KEY")
model = genai.GenerativeModel("gemini-1.5-flash")

# Load the data
df = pd.read_csv("data/clothes_data.csv")
df_sample = df.iloc[5:6]   # process only row 6 for now
print(df.head())


def google_search(query):
    url = "https://google.serper.dev/search"
    headers = {
        "X-API-KEY": SERPER_API_KEY,
        "Content-Type": "application/json"
    }
    enhanced_query = f"{query} Singapore contact information"
    payload = {"q": enhanced_query, "num": 10, "location": "Singapore"}
    
    try:
        response = requests.post(url, headers=headers, json=payload)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"Search error for {query}: {e}")
        return {}


def get_website_domains(search_results):
    """Extract potential website URLs from search results"""
    website_links = []
    
    for item in search_results.get('organic', []):
        link = item.get('link', '')
        if any(domain in link for domain in ['.com', '.sg', '.net', '.org']):
            if not any(social in link.lower() for social in 
                       ['facebook', 'instagram', 'linkedin', 'twitter', 'tiktok']):
                website_links.append(link)
    
    # Deduplicate while preserving order
    seen = set()
    unique_links = []
    for link in website_links:
        if link not in seen:
            seen.add(link)
            unique_links.append(link)
    
    return unique_links


def extract_info_without_ai(company, search_results):
    """Extract information directly from search results without AI"""
    info = {
        "company_name": company,
        "website_link": "Not found",
        "address": "Not found", 
        "phone_number": "Not found",
        "email_address": "Not found",
        "social_media_links": [],
        "description": "Not found"
    }
    
    # Knowledge Graph
    kg = search_results.get("knowledgeGraph", {})
    if kg:
        info["website_link"] = kg.get("website", info["website_link"])
        info["address"] = kg.get("address", info["address"])
        info["phone_number"] = kg.get("phone", info["phone_number"])
        info["email_address"] = kg.get("email", info["email_address"])
        info["description"] = kg.get("description", info["description"])
        if kg.get("social"):
            info["social_media_links"].extend(kg["social"])
    
    # Organic results
    all_text = ""
    websites = get_website_domains(search_results)
    if websites and info["website_link"] == "Not found":
        info["website_link"] = websites[0]
    
    for item in search_results.get('organic', []):
        title = item.get('title', '')
        snippet = item.get('snippet', '')
        link = item.get('link', '')
        
        if any(social in link.lower() for social in 
               ['facebook.com', 'instagram.com', 'linkedin.com', 'twitter.com', 'tiktok.com']):
            info["social_media_links"].append(link)
        
        all_text += f"{title} {snippet} "
    
    # Regex for phone
    if info["phone_number"] == "Not found":
        phone_patterns = [
            r'\+65\s*\d{4}\s*\d{4}',
            r'\d{4}\s*\d{4}',
            r'\(\d{4}\)\s*\d{4}',
        ]
        for pattern in phone_patterns:
            match = re.search(pattern, all_text)
            if match:
                info["phone_number"] = match.group().strip()
                break
    
    # Regex for email
    if info["email_address"] == "Not found":
        email_pattern = r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'
        match = re.search(email_pattern, all_text)
        if match:
            info["email_address"] = match.group()
    
    # Description
    if info["description"] == "Not found":
        snippets = [item.get('snippet', '') for item in search_results.get('organic', [])]
        snippets = [s for s in snippets if s and len(s) > 20]
        if snippets:
            info["description"] = snippets[0]
    
    # Clean socials
    info["social_media_links"] = list(set(info["social_media_links"]))
    info["social_media_links"] = ", ".join(info["social_media_links"]) if info["social_media_links"] else "Not found"
    
    return info


def extract_company_info_with_retry(company, search_results):
    """Try Gemini AI; fallback to regex extraction"""
    try:
        snippets = []
        for item in search_results.get('organic', []):
            title = item.get('title', '')
            snippet = item.get('snippet', '')
            link = item.get('link', '')
            snippets.append(f"- {title}: {snippet} ({link})")
        
        prompt = f"""
        Extract company information from these search results. Return ONLY a JSON object.

        Company: {company}
        Search Results:
        {chr(10).join(snippets)}

        Return this exact JSON format:
        {{
            "company_name": "{company}",
            "website_link": "website or Not found",
            "address": "address or Not found", 
            "phone_number": "phone or Not found",
            "email_address": "email or Not found",
            "social_media_links": "social media links or Not found",
            "description": "business description or Not found"
        }}
        """
        
        response = model.generate_content(prompt)
        response_text = response.text.strip()
        
        if response_text.startswith('```'):
            response_text = '\n'.join(response_text.split('\n')[1:-1])
        
        start_idx = response_text.find('{')
        end_idx = response_text.rfind('}') + 1
        if start_idx != -1 and end_idx > start_idx:
            return json.loads(response_text[start_idx:end_idx])
    except Exception as e:
        print(f"AI extraction failed: {e}")
    
    return extract_info_without_ai(company, search_results)


# Run pipeline
results = []
for i, (_, row) in enumerate(df_sample.iterrows()):
    company = row['entity_name']
    print(f"\nProcessing {i+1}/{len(df_sample)}: {company}")
    
    search_results = google_search(company)
    
    if not search_results.get('organic') and not search_results.get('knowledgeGraph'):
        print(f"  No search results for {company}")
        results.append({
            "company_name": company,
            "website_link": "Not found",
            "address": "Not found",
            "phone_number": "Not found",
            "email_address": "Not found",
            "social_media_links": "Not found",
            "description": "Not found"
        })
        continue
    
    company_info = extract_company_info_with_retry(company, search_results)
    print(f"  Result: {company_info.get('website_link', 'Not found')}")
    results.append(company_info)
    
    time.sleep(2)

# Save results
df_results = pd.DataFrame(results)
df_results.to_csv("data/results.csv", index=False)
print(f"\n✓ Success - Results saved to data/results.csv")
