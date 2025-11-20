import os
import requests
import json
import time
import argparse
from datetime import datetime

# Configuration
SEARCH_TEXT = "Maillot Asse"
VINTED_URL = f"https://www.vinted.fr/api/v2/catalog/items?search_text={SEARCH_TEXT}&order=newest_first&per_page=10"
WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL")
STATE_FILE = "last_seen_id.txt"

def get_vinted_items(session):
    try:
        response = session.get(VINTED_URL)
        if response.status_code == 401 or response.status_code == 403:
             # Refresh session/cookies if needed
             session.get("https://www.vinted.fr/")
             response = session.get(VINTED_URL)
        
        response.raise_for_status()
        return response.json()
    except Exception as e:
        print(f"Error fetching data: {e}")
        return None

def get_item_details(session, item_id):
    """Scrape item page to get description and all photos"""
    try:
        import re
        detail_url = f"https://www.vinted.fr/items/{item_id}"
        print(f"Scraping: {detail_url}", flush=True)
        response = session.get(detail_url, timeout=10)
        response.raise_for_status()
        html = response.text
        
        # Extract description from HTML
        description = ''
        desc_match = re.search(r'<div[^>]*itemprop="description"[^>]*>(.*?)</div>', html, re.DOTALL)
        if desc_match:
            description = desc_match.group(1).strip()
            # Remove HTML tags
            description = re.sub(r'<[^>]+>', '', description)
            description = description.replace('&nbsp;', ' ').strip()
        
        # Extract photo URLs from HTML
        photos = []
        photo_matches = re.findall(r'"url":"(https://images\d+\.vinted\.net/[^"]+)"', html)
        if photo_matches:
            # Deduplicate and take first 3
            seen = set()
            for url in photo_matches:
                if url not in seen and len(photos) < 3:
                    photos.append(url)
                    seen.add(url)
        
        print(f"Scraped: description={len(description)} chars, photos={len(photos)}", flush=True)
        return {'description': description, 'photos': photos}
    except Exception as e:
        print(f"Error scraping item: {e}", flush=True)
        return None


def send_discord_alert(item, scraped_data=None):
    if not WEBHOOK_URL:
        print("No Discord Webhook URL set. Skipping notification.")
        return

    try:
        raw_price = item.get('total_item_price') or item.get('price') or "N/A"
        if isinstance(raw_price, dict):
            price = raw_price.get('amount', 'N/A')
        else:
            price = raw_price

        size = item.get('size_title', 'N/A')
        brand = item.get('brand_title', 'N/A')
        title = item.get('title', 'Nouvel article')
        url = item.get('url', 'https://www.vinted.fr')
        
        # Use scraped data if available
        description = ''
        photos = []
        
        if scraped_data:
            description = scraped_data.get('description', '')
            photos = scraped_data.get('photos', [])
        
        # Fallback to basic photo if no scraped photos
        if not photos:
            if item.get('photo') and isinstance(item['photo'], dict):
                photo_url = item['photo'].get('url')
                if photo_url:
                    photos.append(photo_url)
        
        # Truncate description
        if len(description) > 200:
            description = description[:200] + "..."
        
        # Build description text
        desc_text = f"**{price} €** | Taille: **{size}**\nMarque: {brand}"
        if description:
            desc_text += f"\n\n{description}"

        embed1 = {
            "title": title,
            "url": url,
            "description": desc_text,
            "color": 3447003,
            "footer": {"text": "Vinted Bot"},
            "image": {"url": photos[0]} if len(photos) > 0 else {}
        }
        
        embeds = [embed1]
        
        # Add second photo if available
        if len(photos) > 1:
            embed2 = {
                "url": url,
                "image": {"url": photos[1]}
            }
            embeds.append(embed2)
        
        payload = {"username": "Vinted Bot", "embeds": embeds}
        requests.post(WEBHOOK_URL, json=payload)
        print(f"Sent alert for item {item.get('id')}")

    except Exception as e:
        print(f"Error processing item: {e}")

def load_last_seen_id():
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r") as f:
                return int(f.read().strip())
        except:
            pass
    return 0

def save_last_seen_id(item_id):
    with open(STATE_FILE, "w") as f:
        f.write(str(item_id))

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--duration", type=int, default=0, help="Duration to run in seconds")
    parser.add_argument("--interval", type=int, default=60, help="Interval between checks in seconds")
    args = parser.parse_args()

    print(f"Starting Vinted Bot for '{SEARCH_TEXT}'")
    print(f"Duration: {args.duration}s, Interval: {args.interval}s")

    start_time = time.time()
    
    # Setup session
    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "fr-FR,fr;q=0.9,en-US;q=0.8,en;q=0.7",
        "Referer": "https://www.vinted.fr/",
        "Origin": "https://www.vinted.fr"
    })
    # Init cookies
    try:
        session.get("https://www.vinted.fr/")
    except:
        pass

    last_seen_id = load_last_seen_id()
    print(f"Initial Last Seen ID: {last_seen_id}")

    while True:
        current_time = time.time()
        if args.duration > 0 and (current_time - start_time) > args.duration:
            print("Duration limit reached. Exiting.")
            break

        print(f"[{datetime.now().strftime('%H:%M:%S')}] Checking...")
        
        data = get_vinted_items(session)
        
        if data and 'items' in data:
            items = data['items']
            if items:
                # Filter new items
                new_items = [item for item in items if item['id'] > last_seen_id]
                
                if new_items:
                    print(f"Found {len(new_items)} new items!")
                    # Send alerts (oldest to newest)
                    for item in reversed(new_items):
                        # Try to scrape details
                        scraped = get_item_details(session, item['id'])
                        send_discord_alert(item, scraped)
                    
                    # Update ID
                    last_seen_id = new_items[0]['id']
                    save_last_seen_id(last_seen_id)
                else:
                    print("No new items.")
            else:
                print("No items returned.")
        
        # Wait for next interval
        time.sleep(args.interval)

if __name__ == "__main__":
    main()
