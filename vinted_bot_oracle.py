#!/usr/bin/env python3
"""
Vinted Bot V11.12 - ECONOMY SNIPER
- Redéploiement des optimisations V10.6 (Green Energy)
- Repos 20s pour diviser le coût Railway par 2
- Tri des requêtes (Priorité ASSE)
- Alertes Premium V10.2 conservées
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
    url = f"https://www.vinted.fr/catalog?search_text={query.replace(' ', '+')}&order=newest_first"
    if color_id:
        url += f"&color_ids[]={color_id}"
    return url

def scrape_item_details(page, item_url):
    try:
        # On va sur la page détail
        page.goto(item_url, wait_until='domcontentloaded', timeout=20000)
        time.sleep(1)
        
        # Extraction Photos (Indispensable pour Discord)
        photos = page.evaluate("""() => {
            const imgs = Array.from(document.querySelectorAll('.item-photo--1 img, .item-photos img'));
            return imgs.map(img => img.src).filter(src => src && src.includes('images.vinted'));
        }""")
        
        import re
        id_match = re.search(r'/items/(\d+)', item_url)
        item_id = id_match.group(1) if id_match else "0"

        # On tente l'API pour avoir la description complète
        api_data = page.evaluate(f"""async () => {{
            try {{
                const r = await fetch('/api/v2/items/{item_id}?localize=false');
                return r.ok ? await r.json() : null;
            }} catch(e) {{ return null; }}
        }}""")

        if api_data and 'item' in api_data:
            it = api_data['item']
            return {
                "description": it.get('description', ''),
                "photos": photos,
                "brand": it.get('brand_title', 'N/A'),
                "size": it.get('size_title', 'N/A'),
                "status": it.get('status', 'N/A')
            }
        
        desc = page.evaluate("() => document.querySelector('[itemprop=\"description\"]')?.innerText || ''")
        return {"description": desc, "photos": photos, "brand": "N/A", "size": "N/A", "status": "N/A"}
    except:
        return {"description": "", "photos": [], "brand": "N/A", "size": "N/A", "status": "N/A"}

def extract_items_from_page(page):
    try:
        return page.evaluate("""() => {
            const items = [];
            const grid = document.querySelector('.feed-grid, [class*="feed-grid"]');
            const elements = grid ? grid.querySelectorAll('div[data-testid*="item"]') : document.querySelectorAll('div[data-testid*="item"]');
            
            elements.forEach((el, index) => {
                const a = el.querySelector('a');
                if (!a) return;
                const url = a.href;
                const idMatch = url.match(/items\\/(\\d+)/);
                if (!idMatch) return;
                const id = parseInt(idMatch[1]);
                const rawTitle = a.getAttribute('title') || "";
                const img = el.querySelector('img');
                const priceMatch = el.innerText.match(/\\d+[.,]\\d+\\s*[$€]/);
                const isBoosted = !!el.querySelector('[class*="boost"], [class*="promoted"]');

                items.push({
                    id: id, url: url, title: rawTitle,
                    photo: img?.src || '', price: priceMatch ? priceMatch[0] : 'N/A',
                    is_boosted: isBoosted, index: index
                });
            });
            return items;
        }""")
    except: return []

def send_discord_alert(context, item):
    if not DISCORD_WEBHOOK_URL: return
    try:
        # Pour les détails, on ouvre exceptionnellement les images pour avoir la photo
        p = context.new_page()
        d = scrape_item_details(p, item['url'])
        p.close()
        
        import re
        clean_title = item['title'].split(',')[0].split('·')[0].strip()
        clean_title = re.sub(r'\\d+[.,]\\d+\\s*€.*$', '', clean_title).strip()
        if not clean_title: clean_title = "Maillot ASSE"

        f_desc = clean_text(d['description'])
        desc_preview = f_desc[:1000] + "..." if len(f_desc) > 1000 else (f_desc if f_desc else "Pas de description")
        
        payload = {
            "content": f"@everyone | {clean_title}\n💰 {item['price']} | 📏 {d['size']} | 🏷️ {d['brand']}\n📝 {desc_preview}",
            "username": "Vinted ASSE Bot",
            "avatar_url": "https://images.vinted.net/assets/icon-76x76-precomposed-3e6e4c5f0b8c7e5a5c5e5e5e5e5e5e5e.png",
            "embeds": [{
                "title": f"🔔 {clean_title}", "url": item['url'], "color": 0x09B83E,
                "description": f"**{item['price']}** | Taille: **{d['size']}**\nMarque: **{d['brand']}**\nÉtat: {d.get('status', 'N/A')}\n\n{f_desc[:300]}...",
                "image": {"url": d['photos'][0] if d['photos'] else item['photo']},
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
    log("🚀 Démarrage ECONOMY SNIPER V11.12")
    seen_ids = set()
    initialized_queries = set()
    last_green_check = 0
    last_secondary_check = 0
    last_seen_id = load_last_seen_id()

    while True:
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True, args=['--no-sandbox'])
                context = browser.new_context(
                    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                    locale="fr-FR"
                )
                
                # OPTIMISATION AGRESSIVE (Green Energy)
                def block(route):
                    if route.request.resource_type in ["image", "font", "media"]:
                        route.abort()
                    else:
                        route.continue_()
                context.route("**/*", block)

                now = time.time()
                hour = (datetime.utcnow().hour + 1) % 24
                if 1 <= hour < 7:
                    log("🌙 Veille Nuit (Sommeil)"); browser.close(); time.sleep(600); continue

                # Détermination des requêtes (Optimisé pour le coût)
                queries = [(q, None) for q in PRIORITY_QUERIES]
                if now - last_green_check > 300:
                    queries += [(q, 10) for q in PRIORITY_QUERIES]; last_green_check = now
                if now - last_secondary_check > 900: # Toutes les 15 minutes (au lieu de chaque cycle)
                    queries += [(q, None) for q in SECONDARY_QUERIES]; last_secondary_check = now

                signal.signal(signal.SIGALRM, watchdog_handler); signal.alarm(450)

                for q, c in queries:
                    q_key = f"{q}_{c}"
                    try:
                        log(f"🔎 Check: '{q}'{' [VERTE]' if c else ''}")
                        page = context.new_page()
                        page.goto(get_search_url(q, c), wait_until="domcontentloaded", timeout=30000)
                        time.sleep(1.5)
                        page.wait_for_selector('div[data-testid*="item"]', timeout=15000)
                        
                        items = extract_items_from_page(page)
                        is_new_query = q_key not in initialized_queries
                        
                        for it in items:
                            if it['id'] not in seen_ids:
                                seen_ids.add(it['id'])
                                if not is_new_query and it['id'] > last_seen_id:
                                    if it['is_boosted'] and it['index'] > 2: continue # Filtre anti-vieux
                                    
                                    t = it['title'].lower()
                                    if any(k in t for k in ["asse", "saint", "st-", "sainté"]) and \
                                       (any(k in t for k in ["maillot", "jersey", "camiseta", "trikot", "ensemble"]) or c == 10):
                                        send_discord_alert(context, it)
                                        last_seen_id = max(last_seen_id, it['id']); save_last_seen_id(last_seen_id)
                        
                        initialized_queries.add(q_key)
                        page.close()
                        time.sleep(random.uniform(0.5, 1))
                    except Exception as e:
                        log(f"⚠️ Erreur {q}: {e}")

                browser.close()
                signal.alarm(0)
                log("⏳ Cycle terminé. Repos 20s...") # Repos allongé pour économie
                time.sleep(20)

        except Exception as e:
            log(f"🚨 Bug global : {e}"); time.sleep(30)

if __name__ == "__main__":
    run_bot()
