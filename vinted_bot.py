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

def send_discord_alert(item):
    if not WEBHOOK_URL:
        print("No Discord Webhook URL set. Skipping notification.")
        return

    embed = {
        "title": "Nouveau Maillot ASSE !",
        "description": item['title'],
        "url": item['url'],
        "color": 3447003, # Green-ish
        "fields": [
            {"name": "Prix", "value": f"{item['price']} {item['currency']}", "inline": True},
            {"name": "Taille", "value": item['size_title'], "inline": True},
            {"name": "Marque", "value": item['brand_title'], "inline": True}
        ],
        "image": {"url": item['photo']['url']} if item.get('photo') else {},
        "footer": {"text": f"ID: {item['id']}"}
    }
    
    payload = {
        "username": "Vinted Bot",
        "embeds": [embed]
    }

    try:
        requests.post(WEBHOOK_URL, json=payload)
        print(f"Sent alert for item {item['id']}")
    except Exception as e:
        print(f"Error sending Discord alert: {e}")

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
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "application/json, text/plain, */*"
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
                        send_discord_alert(item)
                    
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
