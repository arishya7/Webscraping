import numbers
import os
import requests
import pandas as pd
import json
import time
import re


SERPER_API_KEY = os.getenv("SERPER_API_KEY")

# Load the data
df = pd.read_csv("data/clothes_data.csv")
df_sample = df[:5]
print(df.head())

#phone validation
def is_valid_singapore_phone(number: str) -> bool:
    """Check if number is valid Singapore phone format"""
    cleaned = re.sub(r'[\s\-\(\)]', '', number)
    if cleaned.startswith('+65'): cleaned = cleaned[3:]
    elif cleaned.startswith('65'): cleaned = cleaned[2:]
    return len(cleaned) == 8 and cleaned.isdigit() and cleaned[0] in '689'

#any international numbers

def extract_extra_numbers(all_text, primary):
    """
    Extract any additional numbers that start with '+'.
    Keeps them if they are different from the primary number.
    """
    # Match anything starting with + and at least 7 digits after
    numbers = re.findall(r'\+\d[\d\s\-()]{6,}', all_text)

    cleaned_numbers = []
    for num in numbers:
        cleaned = re.sub(r'[\s\-\(\)]', '', num) 
        if cleaned != re.sub(r'[\s\-\(\)]', '', primary): 
            cleaned_numbers.append(num.strip())

    return ", ".join(set(cleaned_numbers)) if cleaned_numbers else "Not found"


def is_registration_number(number: str, context: str) -> bool:
    """Check if number is likely a business registration/UEN"""
    cleaned = re.sub(r'[\s\-]', '', number)
    
    # UEN patterns or business context
    if re.match(r'^[0-9]{8,10}[A-Z]?$', cleaned) and len(cleaned) >= 8:
        business_keywords = ['uen', 'reg', 'registration', 'company','acra', 'incorporated', 'roc']
        return any(keyword in context.lower() for keyword in business_keywords)
    return False

def extract_right_phone_number(search_results:dict) -> str:
    """Extract the most probable phone number from candidates"""
    kg_phone = search_results.get("knowledgeGraph", {}).get("phone")
    if kg_phone and is_valid_singapore_phone(kg_phone):
        return kg_phone
    
    # Get all text from search results
    all_text = " ".join([
        f"{item.get('title', '')} {item.get('snippet', '')}" 
        for item in search_results.get('organic', [])
    ])
    
    # Find phone candidates with context
    candidates = []

    ##match with contact format
    for match in re.finditer(r'(?:phone|tel|call|contact|mobile|whatsapp)[\s:]*(\+?65[\s\-]?[689]\d{3}[\s\-]?\d{4}|[689]\d{3}[\s\-]?\d{4})', all_text, re.I):
        candidates.append(('high', match.group(1), match.group(0)))

    ##match with general phone format
    for match in re.finditer(r'\+65[\s\-]?[689]\d{3}[\s\-]?\d{4}', all_text):
        context = all_text[max(0, match.start()-50):match.end()+50]
        candidates.append(('medium', match.group(), context))

    ##match with number length
    for match in re.finditer(r'\b[689]\d{3}[\s\-]?\d{4}\b', all_text):
        context = all_text[max(0, match.start()-80):match.end()+80]
        candidates.append(('low', match.group(), context))

    candidates = sorted(candidates, key=lambda x: {'high':3, 'medium':2, 'low':1}[x[0]], reverse=True)

    for priority, number, context in candidates:
        if is_valid_singapore_phone(number) and not is_registration_number(number, context):
            return number
    
    return "Not found"



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
        "extra_phone": "Not found",
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
        if kg.get("extra_phone"):
            info["extra_phone"] = kg["extra_phone"]
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
        extracted_phone = extract_right_phone_number(search_results)
        if extracted_phone != "Not found":
            info["phone_number"] = extracted_phone

    if info["extra_phone"] == "Not found":
        info["extra_phone"] = extract_extra_numbers(all_text, info["phone_number"])

    
    
    # Extract email addresses
    if info["email_address"] == "Not found":
        email_pattern = r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'
        match = re.search(email_pattern, all_text)
        if match:
            info["email_address"] = match.group()

##address_pattern matching 
    address_pattern = re.compile(
    r'(\d{1,3}[\w\s\-,]+(?:Road|Rd|Street|St|Avenue|Ave|Drive|Dr|Lane|Ln|Way|Place|Pl|Close|Cl|Boulevard|Blk|Building|Centre|Tower|Plaza)[^,.]*?(Singapore\s*\d{4,6}|S\d{4,6})?)',
    re.IGNORECASE
    )

    contact_keywords = ['phone', 'tel', 'call', 'whatsapp', 'email', '@', '+65', 'contact', 'address', 'singapore', 'S\d{6}', '\d{6}']

    #Extract address using regex if not found
    if info["address"] == "Not found":
        for item in search_results.get('organic', []):
            snippet = item.get('snippet', '')
            match = address_pattern.search(snippet)
            if match:
                info["address"] = match.group().strip()
                break

    # Extract description from snippets
    if info["description"] == "Not found":
        descriptions = []
        for item in search_results.get('organic', []):
            snippet = item.get('snippet', '')
            if snippet and len(snippet) > 20:
                if not(address_pattern.search(snippet)) and not any(keyword in snippet.lower() for keyword in contact_keywords):
                    info["description"] = snippet.strip()
                    break
      
    
    # Clean up social media links
    info["social_media_links"] = list(set(info["social_media_links"])) 
    if info["social_media_links"]:
        info["social_media_links"] = ", ".join(info["social_media_links"])
    else:
        info["social_media_links"] = "Not found"
    
    return info


def extract_company_info_fallback(company, search_results):
    """Fallback method without AI - direct extraction from search results"""
    
    print(f"  Using fallback extraction for {company}")
    
    # Debug: Print what we got from search
    print(f"  Search returned {len(search_results.get('organic', []))} organic results")
    if search_results.get('knowledgeGraph'):
        print(f"  Found knowledge graph data")
    
    info = extract_info_without_ai(search_results)
    info["company_name"] = company
    
    return info


def extract_company_info_with_retry(company, search_results, max_retries=0):
    """Extract company info without Gemini, fallback only"""
    return extract_company_info_fallback(company, search_results)


# Process companies
results = []
for i, (_, row) in enumerate(df_sample.iterrows()):
    company = row['entity_name']
    print(f"\nProcessing {i+1}/whole: {company}")
    
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
    company_info = extract_company_info_with_retry(company, search_results)
    print(f"  Result: {company_info.get('website_link', 'Not found')}")
    results.append(company_info)
    
    # Add delay to avoid rate limiting
    time.sleep(2)

# Save results
df_results = pd.DataFrame(results)
df_results.to_csv("data/clothes_phone.csv", index=False)
print(f"\n✓ Success - Results saved")
print(f"Found info for {len([r for r in results if r['website_link'] != 'Not found'])} companies")


