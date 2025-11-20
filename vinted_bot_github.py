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
    """Fetch full details for a specific item to get description and all photos"""
    try:
        detail_url = f"https://www.vinted.fr/api/v2/items/{item_id}"
        response = session.get(detail_url)
        response.raise_for_status()
        data = response.json()
        return data.get('item', {})
    except Exception as e:
        print(f"Error fetching item details: {e}")
        return None

def send_discord_alert(item):
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
        
        # Photos
        photos = []
        if item.get('photos'):
             for p in item['photos']:
                 if isinstance(p, dict) and p.get('url'):
                     photos.append(p['url'])
        
        # Fallback to single photo object if photos list is empty or missing
        if not photos and item.get('photo') and isinstance(item['photo'], dict):
             photos.append(item['photo'].get('url'))

        photo_url_1 = photos[0] if len(photos) > 0 else None
        photo_url_2 = photos[1] if len(photos) > 1 else None
        
        # Description (truncate if too long)
        description = item.get('description', '')
        if len(description) > 200:
            description = description[:200] + "..."

        embed1 = {
            "title": title,
            "url": url,
            "description": f"**{price} €** | Taille: **{size}**\nMarque: {brand}\n\n{description}",
            "color": 3447003,
            "footer": {"text": "Vinted Bot"},
            "image": {"url": photo_url_1} if photo_url_1 else {}
        }
        
        embeds = [embed1]
        
        if photo_url_2:
            embed2 = {
                "url": url,
                "image": {"url": photo_url_2}
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
                        # Fetch full details to get description
                        full_item = get_item_details(session, item['id'])
                        if full_item:
                            send_discord_alert(full_item)
                        else:
                            send_discord_alert(item)  # Fallback to basic info
                    
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
