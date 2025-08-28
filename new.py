import numbers
import os
import google.generativeai as genai
import requests
import pandas as pd
import json
import time
import re

genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
SERPER_API_KEY = os.getenv("SERPER_API_KEY")
model = genai.GenerativeModel("gemini-1.5-flash")

# Load the data
df = pd.read_csv("data/clothes_data.csv")
df_sample = df.iloc[:10] 
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
        phone_patterns = [
            r'\+65\s*\d{4}\s*\d{4}',  # Singapore format
            r'\d{4}\s*\d{4}',         # Local format
            r'\(\d{4}\)\s*\d{4}',     # (1234) 5678
        ]
        for pattern in phone_patterns:
            match = re.search(pattern, all_text)
            if match:
                info["phone_number"] = match.group().strip()
                break
    
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


def extract_company_info_with_retry(company, search_results, max_retries=3):
    """Extract company info with retry logic and fallback"""
    
    for attempt in range(max_retries):
        try:
            snippets = []

            # Extract organic search results
            for item in search_results.get('organic', []):
                title = item.get('title', '')
                snippet = item.get('snippet', '')
                link = item.get('link', '')
                snippets.append(f"- {title}: {snippet} ({link})")
           
            # Extract knowledge graph information
            knowledge_snippet = search_results.get("knowledgeGraph", {})
            if knowledge_snippet:
                for key in ["title", "description", "website", "address", "phone", "email"]:
                    if key in knowledge_snippet:
                        snippets.append(f"- {key.title()}: {knowledge_snippet[key]}")
                
                if "social" in knowledge_snippet:
                    for link in knowledge_snippet.get("social", []):
                        snippets.append(f"- Social: {link}")

            if not snippets:
                print(f"  No search data found for {company}")
                return extract_company_info_fallback(company, search_results)

            prompt = f"""
            Extract company information from these search results. Return ONLY a JSON object.

            Company: {company}
            Search Results:
            {chr(10).join(snippets)}  # Limit to avoid token limits

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
            
            # Clean response
            if response_text.startswith('```'):
                response_text = '\n'.join(response_text.split('\n')[1:-1])
            
            start_idx = response_text.find('{')
            end_idx = response_text.rfind('}') + 1
            
            if start_idx != -1 and end_idx > start_idx:
                json_text = response_text[start_idx:end_idx]
                result = json.loads(json_text)
                print(f"  ✓ AI extraction successful for {company}")
                return result
            else:
                raise ValueError("No valid JSON found in response")
                
        except Exception as e:
            print(f"  Attempt {attempt + 1} failed for {company}: {e}")
            if attempt == max_retries - 1:
                print(f"  Falling back to direct extraction for {company}")
                return extract_company_info_fallback(company, search_results)
            else:
                time.sleep(2 ** attempt) 
    return extract_company_info_fallback(company, search_results)


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
    company_info = extract_company_info_with_retry(company, search_results)
    print(f"  Result: {company_info.get('website_link', 'Not found')}")
    results.append(company_info)
    
    # Add delay to avoid rate limiting
    time.sleep(2)

# Save results
df_results = pd.DataFrame(results)
df_results.to_csv("data/results.csv", index=False)
print(f"\n✓ Success - Results saved to data/results.csv")
print(f"Found info for {len([r for r in results if r['website_link'] != 'Not found'])} companies")


