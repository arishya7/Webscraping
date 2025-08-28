import pandas as pd
from openai import OpenAI

client = OpenAI(api_key="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")

# Load the Excel file and extract domains
excel_file = "clothes_data.xlsx"
df = pd.read_excel(excel_file)
domains = df['entity_name'].dropna().tolist() 
domains = domains[:10]  

agentql = "OsD_LML2i9DogYK8EZJlcfdw9xah96v2NoifKxd2DtYv6LXdKit_bg"

import agentql
from playwright.sync_api import sync_playwright
from pyairtable import Api
from dotenv import load_dotenv


def extract_company_info_with_retry(company, search_results, max_retries=0):
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
