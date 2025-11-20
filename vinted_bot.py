import os
import requests
import time
import threading
from flask import Flask
from datetime import datetime

# Configuration
SEARCH_TEXT = "Maillot Asse"
VINTED_URL = f"https://www.vinted.fr/api/v2/catalog/items?search_text={SEARCH_TEXT}&order=newest_first&per_page=10"
WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL")
STATE_FILE = "last_seen_id.txt"

app = Flask(__name__)

def get_vinted_items(session):
    try:
        response = session.get(VINTED_URL)
        if response.status_code == 401 or response.status_code == 403:
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
        
        photo_url = None
        if item.get('photo') and isinstance(item['photo'], dict):
            photo_url = item['photo'].get('url')

        embed = {
            "title": title,
            "url": url,
            "description": f"**{price} €** | Taille: **{size}**\nMarque: {brand}",
            "color": 3447003,
            "footer": {"text": "Vinted Bot"},
            "image": {"url": photo_url} if photo_url else {}
        }
        
        payload = {"username": "Vinted Bot", "embeds": [embed]}
        requests.post(WEBHOOK_URL, json=payload)
        print(f"Sent alert for item {item.get('id')}")

    except Exception as e:
        print(f"Error processing item: {e}")

def load_last_seen_id():
    # On Render, files are ephemeral (lost on restart), but it's better than nothing.
    # For persistence, we would need a database, but let's keep it simple for now.
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

def run_bot_loop():
    print("Starting Vinted Bot Loop...")
    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "application/json, text/plain, */*"
    })
    try:
        session.get("https://www.vinted.fr/")
    except:
        pass

    last_seen_id = load_last_seen_id()
    
    while True:
        try:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] Checking Vinted...")
            data = get_vinted_items(session)
            
            if data and 'items' in data:
                items = data['items']
                if items:
                    new_items = [item for item in items if item['id'] > last_seen_id]
                    if new_items:
                        print(f"Found {len(new_items)} new items!")
                        for item in reversed(new_items):
                            send_discord_alert(item)
                        last_seen_id = new_items[0]['id']
                        save_last_seen_id(last_seen_id)
            
            time.sleep(20) # Check every 20 seconds
        except Exception as e:
            print(f"Loop error: {e}")
            time.sleep(20)

@app.route('/')
def home():
    return "Vinted Bot is Alive!"

if __name__ == "__main__":
    print("--- SYSTEM STARTUP ---")
    # Start bot in background thread
    print("Launching Bot Thread...")
    thread = threading.Thread(target=run_bot_loop)
    thread.daemon = True
    thread.start()
    print("Bot Thread Launched!")
    
    # Start web server (needed for Render/UptimeRobot)
    port = int(os.environ.get("PORT", 5000))
    print(f"Starting Flask Server on port {port}...")
    app.run(host='0.0.0.0', port=port)
