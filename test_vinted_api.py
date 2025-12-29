import requests
import json

# Test script to see what Vinted API returns
session = requests.Session()
session.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "fr-FR,fr;q=0.9",
    "Referer": "https://www.vinted.fr/",
    "Origin": "https://www.vinted.fr"
})

# Init session
session.get("https://www.vinted.fr/")

# Get search results
url = "https://www.vinted.fr/api/v2/catalog/items?search_text=Maillot%20Asse&order=newest_first&per_page=3"
print(f"Fetching: {url}\n")
response = session.get(url)
data = response.json()

if 'items' in data and data['items']:
    first_item = data['items'][0]
    item_id = first_item['id']
    
    print("=" * 60)
    print("SEARCH RESULT (first item):")
    print("=" * 60)
    print(f"ID: {item_id}")
    print(f"Title: {first_item.get('title', 'N/A')}")
    print(f"Description in search: '{first_item.get('description', 'NOT PRESENT')}'")
    print(f"Photos in search: {len(first_item.get('photos', []))}")
    print()
    
    # Get full details
    detail_url = f"https://www.vinted.fr/api/v2/items/{item_id}"
    print(f"Fetching details: {detail_url}\n")
    detail_response = session.get(detail_url)
    detail_data = detail_response.json()
    
    if 'item' in detail_data:
        full_item = detail_data['item']
        print("=" * 60)
        print("FULL ITEM DETAILS:")
        print("=" * 60)
        print(f"ID: {full_item.get('id')}")
        print(f"Title: {full_item.get('title', 'N/A')}")
        desc = full_item.get('description', '')
        print(f"Description length: {len(desc)}")
        print(f"Description: {desc[:200]}...")
        print(f"Photos: {len(full_item.get('photos', []))}")
        print()
        
        # Show photo URLs
        if full_item.get('photos'):
            print("Photo URLs:")
            for i, photo in enumerate(full_item['photos'][:3]):
                print(f"  {i+1}. {photo.get('url', 'N/A')}")
