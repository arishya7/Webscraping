import os
import openai
import requests
import pandas as pd
import json
import time
import re

from openai import OpenAI


client = OpenAI(api_key="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")
SERPER_API_KEY = os.getenv("SERPER_API_KEY")

# Load the data
df = pd.read_csv("data/clothes_data.csv")
df_sample = df.iloc[:10] 
print(df.head())


def is_valid_phone(number:str) -> bool:
    number = number.replace(" ", "").replace("-", "")
    if number.startswith("+65"):
        number = number[3:]
    return len(number) == 8 and number.isdigit() 

def is_probable_uen(number:str) -> bool:
    return bool(re.match(r'^[0-9]{8}[A-Z]$', number))

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
        print(f"Search error for {q}: {e}")
        return {}


def extract_info_without_ai(search_results):
    """Extract information directly from search results without using AI"""
    info = {
        "company_name": "Not found",
        "website_link": "Not found",
        "address": "Not found", 
        "phone_number": "Not found",
        "email_address": "Not found",
        "social_media_links": [],
        "description": "Not found"
    }
    
    # Extract from knowledge graph first (most reliable)
    kg = search_results.get("knowledgeGraph", {})
    if kg:
        if kg.get("website"):
            info["website_link"] = kg["website"]
        if kg.get("address"):
            info["address"] = kg["address"]
        if kg.get("phone"):
            info["phone_number"] = kg["phone"]
        if kg.get("email"):
            info["email_address"] = kg["email"]
        if kg.get("description"):
            info["description"] = kg["description"]
        if kg.get("social"):
            info["social_media_links"].extend(kg["social"])
    
    # Extract from organic results
    all_text = ""
    for item in search_results.get('organic', []):
        title = item.get('title', '')
        snippet = item.get('snippet', '')
        link = item.get('link', '')
        
        # Check if this is the main website
        if info["website_link"] == "Not found" and any(domain in link for domain in ['.com', '.sg', '.net', '.org']):
            if not any(social in link.lower() for social in ['facebook', 'instagram', 'linkedin', 'twitter', 'tiktok']):
                info["website_link"] = link
        
        # Collect social media links
        if any(social in link.lower() for social in ['facebook.com', 'instagram.com', 'linkedin.com', 'twitter.com', 'tiktok.com']):
            info["social_media_links"].append(link)
        
        # Collect all text for pattern matching
        all_text += f"{title} {snippet} "
    
    # Extract phone numbers using regex
    if info["phone_number"] == "Not found":
        match = re.search(r'(\+65\s*)?(6|8|9)\d{3}\s*\d{4}', all_text)
    if match:
        info["phone_number"] = match.group().strip()

    if not is_valid_phone(info["phone_number"]) or is_probable_uen(info["phone_number"]):
        info["phone_number"] = "Not found"
    
    # Extract email addresses
    if info["email_address"] == "Not found":
        email_pattern = r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'
        match = re.search(email_pattern, all_text)
        if match:
            info["email_address"] = match.group()
    
    # Extract description from snippets
    if info["description"] == "Not found":
        descriptions = []
        for item in search_results.get('organic', []):
            snippet = item.get('snippet', '')
            if snippet and len(snippet) > 20:
                descriptions.append(snippet)
        if descriptions:
            info["description"] = descriptions[0]  
    
    # Clean up social media links
    info["social_media_links"] = list(set(info["social_media_links"])) 
    if info["social_media_links"]:
        info["social_media_links"] = ", ".join(info["social_media_links"])
    else:
        info["social_media_links"] = "Not found"
    
    return info



def extract_company_info_with_openai(company, search_results):
    snippets = []
    for item in search_results.get("organic", []):
        title = item.get("title", "")
        snippet = item.get("snippet", "")
        link = item.get("link", "")
        snippets.append(f"- {title}: {snippet} ({link})")

    knowledge_snippet = search_results.get("knowledgeGraph", {})
    if knowledge_snippet:
        for key in ["title", "description", "website", "address", "phone", "email"]:
            if key in knowledge_snippet:
                snippets.append(f"- {key.title()}: {knowledge_snippet[key]}")
        if "social" in knowledge_snippet:
            for link in knowledge_snippet.get("social", []):
                snippets.append(f"- Social: {link}")

    if not snippets:
        return extract_info_without_ai(search_results)

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

    response = client.chat.completions.create(
        model="gpt-4o-mini",  # or gpt-4.1 if you want higher accuracy
        messages=[
            {"role": "system", "content": "You are a data extraction assistant."},
            {"role": "user", "content": prompt}
        ],
        temperature=0
    )

    response_text = response.choices[0].message.content.strip()

    try:
        json_text = re.search(r"\{.*\}", response_text, re.S).group()
        result = json.loads(json_text)
        return result
    except Exception:
        return extract_info_without_ai(search_results)



# Process companies
results = []
for i, (_, row) in enumerate(df_sample.iterrows()):
    company = row['entity_name']
    print(f"\nProcessing {i+1}/10: {company}")
    
    # Search for company
    search_results = google_search(company)
    
    if not search_results.get('organic') and not search_results.get('knowledgeGraph'):
        print(f"  No search results found for {company}")
        results.append({
            "company_name": {company},
            "website_link": "Not found",
            "address": "Not found", 
            "phone_number": "Not found",
            "email_address": "Not found",
            "social_media_links": "Not found",
            "description": "Not found"
        })
        continue
    
    # Extract company info
    company_info = extract_company_info_with_openai(company, search_results)
    print(f"  Result: {company_info.get('website_link', 'Not found')}")
    results.append(company_info)
    
    # Add delay to avoid rate limiting
    time.sleep(2)

# Save results
df_results = pd.DataFrame(results)
df_results.to_csv("data/results.csv", index=False)
print(f"\n✓ Success - Results saved to data/results.csv")
print(f"Found info for {len([r for r in results if r['website_link'] != 'Not found'])} companies")


