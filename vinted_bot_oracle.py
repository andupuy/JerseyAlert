#!/usr/bin/env python3
"""
Vinted Bot V11.9 - ZERO LATENCY SNIPER
- Retour à la détection instantanée (Toutes les requêtes à chaque cycle)
- Suppression des délais de 20 min (Sniper total)
- Optimisation Browser Persistant (Maintien du coût $0.00)
- Bypass Cache Vinted (&v=timestamp)
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
# On fusionne tout pour un Sniping total comme avant
SEARCH_QUERIES = PRIORITY_QUERIES + SECONDARY_QUERIES

DISCORD_WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL")
STATE_FILE = "last_seen_id.txt"

def log(message):
    timestamp = datetime.now().strftime('%H:%M:%S')
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

def clean_text(text):
    if not text: return ""
    import re
    text = re.sub(r'(?i)enlevé\s*!?', '', text)
    text = re.sub(r'(?i)nouveau\s*!?', '', text)
    text = re.sub(r'\s+', ' ', text)
    return text.strip()

def get_search_url(query, color_id=None):
    # Ajout d'un paramètre v= pour forcer Vinted à ne pas servir de cache
    v = int(time.time())
    url = f"https://www.vinted.fr/catalog?search_text={query.replace(' ', '+')}&order=newest_first&v={v}"
    if color_id:
        url += f"&color_ids[]={color_id}"
    return url

def scrape_item_details(page, item_url):
    try:
        log(f"🔎 Détails : {item_url}")
        page.goto(item_url, wait_until='domcontentloaded', timeout=15000)
        time.sleep(1)

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
            it = api_data['item']
            photos = [p.get('url') for p in it.get('photos', [])]
            return {
                "description": it.get('description', ''),
                "photos": photos,
                "brand": it.get('brand_title', 'N/A'),
                "size": it.get('size_title', 'N/A'),
                "status": it.get('status', 'N/A')
            }
        
        # Fallback DOM
        details = page.evaluate("""() => {
            const desc = document.querySelector('[itemprop="description"]')?.innerText || "";
            const imgs = Array.from(document.querySelectorAll('.item-photo--1 img, .item-photos img')).map(i => i.src);
            return { description: desc, photos: imgs };
        }""")
        return {
            "description": details['description'],
            "photos": details['photos'],
            "brand": "N/A", "size": "N/A", "status": "N/A"
        }
    except:
        return {"description": "", "photos": [], "brand": "N/A", "size": "N/A", "status": "N/A"}

def extract_items_from_page(page):
    try:
        return page.evaluate("""() => {
            const items = [];
            document.querySelectorAll('div[data-testid*="item"]').forEach(el => {
                const a = el.querySelector('a');
                if (!a) return;
                const id = parseInt(a.href.match(/items\\/(\\d+)/)[1]);
                const rawTitle = a.getAttribute('title') || "";
                const img = el.querySelector('img');
                const priceMatch = el.innerText.match(/\\d+[.,]\\d+\\s*[$€]/);
                
                let brand = 'N/A', size = 'N/A';
                if (rawTitle.includes('marque:')) brand = rawTitle.match(/marque:\\s*([^,]+)/i)?.[1] || 'N/A';
                if (rawTitle.includes('taille:')) size = rawTitle.match(/taille:\\s*([^,]+)/i)?.[1] || 'N/A';

                items.push({
                    id: id, url: a.href, title: rawTitle,
                    photo: img?.src || '', price: priceMatch ? priceMatch[0] : 'N/A',
                    brand: brand, size: size
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
        
        import re
        clean_title = item['title'].split(',')[0].split('·')[0].strip()
        clean_title = re.sub(r'\\d+[.,]\\d+\\s*€.*$', '', clean_title).strip()
        if not clean_title: clean_title = "Maillot ASSE"

        f_brand = d['brand'] if d['brand'] != 'N/A' else item['brand']
        f_size = d['size'] if d['size'] != 'N/A' else item['size']
        f_desc = clean_text(d['description'])
        f_photo = d['photos'][0] if d['photos'] else item['photo']
        desc_preview = f_desc[:1000] + "..." if len(f_desc) > 1000 else (f_desc if f_desc else "Pas de description")
        
        payload = {
            "content": f"@everyone | {clean_title}\n💰 {item['price']} | 📏 {f_size} | 🏷️ {f_brand}\n📝 {desc_preview}",
            "username": "Vinted ASSE Bot",
            "avatar_url": "https://images.vinted.net/assets/icon-76x76-precomposed-3e6e4c5f0b8c7e5a5c5e5e5e5e5e5e5e.png",
            "embeds": [{
                "title": f"🔔 {clean_title}", "url": item['url'], "color": 0x09B83E,
                "description": f"**{item['price']}** | Taille: **{f_size}**\nMarque: **{f_brand}**\nÉtat: {d.get('status', 'N/A')}\n\n{f_desc[:300]}...",
                "image": {"url": f_photo},
                "footer": {"text": f"Vinted Bot • ID: {item['id']}"},
                "timestamp": datetime.utcnow().isoformat() + "Z"
            }]
        }
        requests.post(DISCORD_WEBHOOK_URL, json=payload, timeout=10)
        log(f"✅ Alerte envoyée #{item['id']}")
    except Exception as e:
        log(f"❌ Erreur Discord: {e}")

def watchdog_handler(signum, frame):
    log("🚨 WATCHDOG !"); os._exit(1)

def run_bot():
    log("🚀 Démarrage ZERO LATENCY SNIPER V11.9")
    seen_ids = set()
    last_green_check = 0
    last_seen_id = load_last_seen_id()
    is_initial = True
    cycle_count = 0

    while True:
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True, args=['--no-sandbox'])
                context = browser.new_context(
                    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                    locale="fr-FR"
                )
                
                # OPTIMISATION ENERGY
                def block(route):
                    if route.request.resource_type in ["image", "font", "media"]: route.abort()
                    else: route.continue_()
                context.route("**/*", block)

                search_page = context.new_page()

                while cycle_count < 20:
                    now = time.time()
                    hour = (datetime.utcnow().hour + 1) % 24
                    if 1 <= hour < 7:
                        log("🌙 Sommeil..."); time.sleep(600); continue

                    # RETOUR AU SNIPING TOTAL : On lance TOUT à chaque fois
                    queries = [(q, None) for q in SEARCH_QUERIES]
                    
                    # On ajoute quand même le scan vert pour les maillots prioritaires
                    if now - last_green_check > 300:
                        queries += [(q, 10) for q in PRIORITY_QUERIES]
                        last_green_check = now

                    log(f"🚀 Cycle {cycle_count}/20 - Sniper Actif ({len(queries)} requêtes)")
                    signal.signal(signal.SIGALRM, watchdog_handler); signal.alarm(450)

                    for q, c in queries:
                        try:
                            log(f"🔎 Check: '{q}'{' [VERTE]' if c else ''}")
                            search_page.goto(get_search_url(q, c), wait_until="domcontentloaded", timeout=30000)
                            time.sleep(1.2)
                            search_page.wait_for_selector('div[data-testid*="item"]', timeout=15000)
                            
                            items = extract_items_from_page(search_page)
                            for it in items:
                                if it['id'] not in seen_ids:
                                    seen_ids.add(it['id'])
                                    if not is_initial and it['id'] > last_seen_id:
                                        t_low = it['title'].lower()
                                        if any(k in t_low for k in ["asse", "saint", "st-", "sainté"]) and \
                                           (any(k in t_low for k in ["maillot", "jersey", "camiseta", "trikot", "ensemble"]) or c == 10):
                                            send_discord_alert(context, it)
                                            last_seen_id = max(last_seen_id, it['id']); save_last_seen_id(last_seen_id)
                            time.sleep(random.uniform(0.3, 0.7))
                        except Exception as e:
                            log(f"⚠️ Erreur {q}: {str(e)[:40]}")
                    
                    is_initial = False; cycle_count += 1; signal.alarm(0)
                    log(f"⏳ Repos 5s...")
                    time.sleep(5) # Sniping agressif

                browser.close(); cycle_count = 0; log("🔄 Refresh...")
        except Exception as e:
            log(f"🚨 Bug: {e}"); time.sleep(30)

if __name__ == "__main__":
    run_bot()
