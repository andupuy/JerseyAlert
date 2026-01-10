#!/usr/bin/env python3
"""
Vinted Bot V11.1 - SNIPER STABLE
- Optimisation Green Energy (Bloque images/polices/médias, garde CSS)
- Navigateur persistant avec rotation d'identité
- Gestion des Timeouts renforcée
"""

import os
import sys
import time
import random
import requests
import signal
from datetime import datetime
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout

# Configuration
PRIORITY_QUERIES = ["Maillot Asse", "Maillot Saint-Etienne", "Maillot St Etienne"]
SECONDARY_QUERIES = ["Jersey Asse", "Jersey Saint-Etienne", "Maglia Asse", "Camiseta Asse", "Ensemble Asse", "Trikot Asse"]
SEARCH_QUERIES = PRIORITY_QUERIES + SECONDARY_QUERIES

DISCORD_WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL")
STATE_FILE = "last_seen_id.txt"

def log(message):
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    print(f"[{timestamp}] {message}", flush=True)

def load_last_seen_id():
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r") as f:
                return int(f.read().strip())
        except: pass
    return 0

def save_last_seen_id(item_id):
    with open(STATE_FILE, "w") as f:
        f.write(str(item_id))

def get_search_url(query, color_id=None):
    url = f"https://www.vinted.fr/catalog?search_text={query.replace(' ', '+')}&order=newest_first"
    if color_id:
        url += f"&color_ids[]={color_id}"
    return url

def clean_text(text):
    if not text: return ""
    import re
    text = re.sub(r'(?i)enlevé\s*!?', '', text)
    text = re.sub(r'(?i)nouveau\s*!?', '', text)
    text = re.sub(r'\s+', ' ', text)
    return text.strip()

def scrape_item_details(page, item_url):
    try:
        page.goto(item_url, wait_until='domcontentloaded', timeout=20000)
        photos = page.evaluate("""() => {
            const imgs = Array.from(document.querySelectorAll('.item-photo--1 img, .item-photos img'));
            return imgs.map(img => img.src).filter(src => src);
        }""")
        photos = list(dict.fromkeys(photos))
        
        import re
        id_match = re.search(r'/items/(\d+)', item_url)
        item_id = id_match.group(1) if id_match else "0"

        api_data = page.evaluate(f"""async () => {{
            try {{
                const r = await fetch('/api/v2/items/{item_id}?localize=false');
                return r.ok ? await r.json() : null;
            }} catch(e) {{ return null; }}
        }}""")
        
        if api_data and 'item' in api_data:
            i = api_data['item']
            return {
                "description": i.get('description', ''),
                "photos": photos,
                "brand": i.get('brand_title', 'N/A'),
                "size": i.get('size_title', 'N/A'),
                "status": i.get('status', 'N/A')
            }
        return {"description": "", "photos": photos, "brand": "N/A", "size": "N/A", "status": "N/A"}
    except:
        return {"description": "", "photos": [], "brand": "N/A", "size": "N/A", "status": "N/A"}

def extract_items_from_page(page):
    try:
        return page.evaluate("""() => {
            const items = [];
            const els = document.querySelectorAll('div[data-testid*="item"], div[class*="feed-grid__item"]');
            els.forEach(el => {
                const a = el.querySelector('a');
                if (!a) return;
                const id = parseInt(a.href.match(/items\\/(\\d+)/)[1]);
                const img = el.querySelector('img');
                items.push({
                    id: id,
                    url: a.href,
                    title: a.getAttribute('title') || img?.alt || 'Maillot ASSE',
                    photo: img?.src || '',
                    price: el.innerText.match(/\\d+[.,]\\d+\\s*[$€]/)?.[0] || 'N/A'
                });
            });
            return items;
        }""")
    except: return []

def send_discord_alert(context, item):
    if not DISCORD_WEBHOOK_URL: return
    try:
        p = context.new_page()
        d = scrape_item_details(p, item['url'])
        p.close()
        
        desc = d['description'][:300] + "..." if len(d['description']) > 300 else d['description']
        payload = {
            "content": f"@everyone | 🔔 {item['title']}\n💰 {item['price']} | 📏 {d['size']} | 🏷️ {d['brand']}\n📝 {desc}",
            "embeds": [{
                "title": item['title'],
                "url": item['url'],
                "color": 0x09B83E,
                "image": {"url": d['photos'][0] if d['photos'] else item['photo']},
                "timestamp": datetime.utcnow().isoformat() + "Z"
            }]
        }
        requests.post(DISCORD_WEBHOOK_URL, json=payload, timeout=10)
        log(f"✅ Alerte envoyée #{item['id']}")
    except Exception as e:
        log(f"❌ Erreur alerte: {e}")

def watchdog_handler(signum, frame):
    log("🚨 Watchdog: Bot figé, restart !")
    os._exit(1)

def run_bot():
    log("🚀 Démarrage SNIPER V11.1")
    seen_ids = set()
    last_green_check = 0
    last_secondary_check = 0
    last_seen_id = load_last_seen_id()
    is_initial = True

    while True:
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True, args=['--no-sandbox'])
                ua = f"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/{random.randint(110, 120)}.0.0.0 Safari/537.36"
                context = browser.new_context(user_agent=ua, locale='fr-FR')
                
                # OPTIMISATION ENERGY (Keep CSS, block others)
                def block(route):
                    if route.request.resource_type in ["image", "font", "media"]: route.abort()
                    else: route.continue_()
                context.route("**/*", block)

                for cycle in range(20):
                    now = time.time()
                    # Veille nuit
                    hour = (datetime.utcnow().hour + 1) % 24
                    if 1 <= hour < 7:
                        log("🌙 Sommeil..."); time.sleep(600); continue

                    queries = [(q, None) for q in PRIORITY_QUERIES]
                    if now - last_green_check > 300:
                        queries += [(q, 10) for q in PRIORITY_QUERIES]; last_green_check = now
                    if now - last_secondary_check > 1200:
                        queries += [(q, None) for q in SECONDARY_QUERIES]; last_secondary_check = now

                    log(f"🔎 Cycle {cycle}/20 - {len(queries)} requêtes")
                    signal.signal(signal.SIGALRM, watchdog_handler)
                    signal.alarm(300)

                    for q, c in queries:
                        try:
                            page = context.new_page()
                            page.goto(get_search_url(q, c), wait_until="domcontentloaded", timeout=30000)
                            
                            # On attend 2s que le JS de Vinted s'exécute
                            time.sleep(2)
                            
                            # Vérification titre si erreur
                            if "Access Denied" in page.title() or "Captcha" in page.title():
                                log(f"🚫 Blocage détecté sur {q} ! ({page.title()})")
                                page.close(); break

                            items = extract_items_from_page(page)
                            for it in items:
                                if it['id'] not in seen_ids:
                                    seen_ids.add(it['id'])
                                    if not is_initial and it['id'] > last_seen_id:
                                        # FILTRE DE SÉCURITÉ (Match Club & Article)
                                        title_low = it['title'].lower()
                                        kw_item = ["maillot", "jersey", "maglia", "camiseta", "ensemble", "trikot"]
                                        kw_team = ["asse", "saint etienne", "saint-etienne", "st etienne", "st-etienne", "saint étienne", "sainté"]
                                        
                                        has_item = any(k in title_low for k in kw_item)
                                        has_team = any(k in title_low for k in kw_team)
                                        
                                        # Match si (Maillot + Club) OU (Scan Vert + Club)
                                        if (has_item and has_team) or (c == 10 and has_team):
                                            send_discord_alert(context, it)
                                            last_seen_id = it['id']; save_last_seen_id(it['id'])
                            page.close()
                            time.sleep(random.uniform(1, 3))
                        except Exception as e:
                            log(f"⚠️ Erreur {q}: {str(e)[:50]}")
                    
                    is_initial = False
                    signal.alarm(0)
                    time.sleep(20)

                browser.close()
                log("🔄 Rotation navigateur...")
        except Exception as e:
            log(f"🚨 Bug global: {e}"); time.sleep(30)

if __name__ == "__main__":
    run_bot()
