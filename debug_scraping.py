import requests
import re

session = requests.Session()
session.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "fr-FR,fr;q=0.9",
})

# Get the page
url = "https://www.vinted.fr/items/7602819966"
print(f"Fetching: {url}\n")
response = session.get(url)

print(f"Status: {response.status_code}")
print(f"Content length: {len(response.text)} chars")
print("\n" + "="*60)

# Save to file for inspection
with open("vinted_page.html", "w", encoding="utf-8") as f:
    f.write(response.text)
print("Saved to vinted_page.html")

# Look for description patterns
if 'description' in response.text.lower():
    print("\n✓ Found 'description' in HTML")
    # Show context around description
    idx = response.text.lower().find('description')
    print(f"Context: ...{response.text[max(0,idx-100):idx+200]}...")
else:
    print("\n✗ 'description' not found in HTML")

# Look for image URLs
image_matches = re.findall(r'https://images\d+\.vinted\.net/[^\s"\'<>]+', response.text)
if image_matches:
    print(f"\n✓ Found {len(image_matches)} image URLs")
    for i, url in enumerate(image_matches[:3]):
        print(f"  {i+1}. {url[:80]}...")
else:
    print("\n✗ No image URLs found")
