#!/usr/bin/env python3
"""
Vinted Bot V11.11 - ANTI-OLD SNIPER
- Initialisation intelligente par requête (évite les remontées d'articles vieux de 2j)
- Filtrage des articles "Boostés" ou "Sponsorisés" hors timing
- Architecture V10.x stable
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
        page.goto(item_url, wait_until='domcontentloaded', timeout=20000)
        time.sleep(1)
        
        photos = page.evaluate("""() => {
            const imgs = Array.from(document.querySelectorAll('.item-photo--1 img, .item-photos img'));
            return imgs.map(img => img.src).filter(src => src && src.includes('images.vinted'));
        }""")
        
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
            // On cherche uniquement dans le grid principal pour éviter les suggestions "Pour vous" en bas
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
                
                // Détection d'article "Boosté" (souvent une classe spécifique ou badge)
                const isBoosted = !!el.querySelector('[class*="boost"], [class*="promoted"]');

                items.push({
                    id: id, url: url, title: rawTitle,
                    photo: img?.src || '', price: priceMatch ? priceMatch[0] : 'N/A',
                    is_boosted: isBoosted,
                    index: index // Pour savoir s'il est au début du grid
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
        
        f_brand = d['brand'] if d['brand'] != 'N/A' else 'N/A'
        f_size = d['size'] if d['size'] != 'N/A' else 'N/A'
        f_desc = clean_text(d['description'])
        f_photo = d['photos'][0] if d['photos'] else item['photo']
        
        import re
        clean_title = item['title'].split(',')[0].split('·')[0].strip()
        clean_title = re.sub(r'\\d+[.,]\\d+\\s*€.*$', '', clean_title).strip()
        if not clean_title: clean_title = "Maillot ASSE"

        desc_full = f_desc if f_desc else "Pas de description"
        desc_preview = desc_full[:1000] + "..." if len(desc_full) > 1000 else desc_full

        payload = {
            "content": f"@everyone | {clean_title}\n💰 {item['price']} | 📏 {f_size} | 🏷️ {f_brand}\n📝 {desc_preview}",
            "username": "Vinted ASSE Bot",
            "avatar_url": "https://images.vinted.net/assets/icon-76x76-precomposed-3e6e4c5f0b8c7e5a5c5e5e5e5e5e5e5e.png",
            "embeds": [{
                "title": f"🔔 {clean_title}", "url": item['url'], "color": 0x09B83E,
                "description": f"**{item['price']}** | Taille: **{f_size}**\nMarque: **{f_brand}**\nÉtat: {d.get('status', 'N/A')}\n\n{desc_full[:300]}...",
                "image": {"url": f_photo},
                "footer": {"text": f"Vinted Bot • ID: {item['id']}"},
                "timestamp": datetime.utcnow().isoformat() + "Z"
            }]
        }
        requests.post(DISCORD_WEBHOOK_URL, json=payload, timeout=10)
        log(f"✅ Alerte envoyée #{item['id']}")
    except Exception as e:
        log(f"❌ Erreur alerte: {e}")

def watchdog_handler(signum, frame):
    log("🚨 WATCHDOG !"); os._exit(1)

def run_bot():
    log("🚀 Démarrage ANTI-OLD SNIPER V11.11")
    seen_ids = set()
    initialized_queries = set() # Pour ne pas alerter sur la première fois d'une requête
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
                
                def block(route):
                    if route.request.resource_type in ["image", "font", "media"]: route.abort()
                    else: route.continue_()
                context.route("**/*", block)

                now = time.time()
                hour = (datetime.utcnow().hour + 1) % 24
                if 1 <= hour < 7:
                    log("🌙 Sommeil..."); browser.close(); time.sleep(600); continue

                queries = [(q, None) for q in PRIORITY_QUERIES]
                if now - last_green_check > 300:
                    queries += [(q, 10) for q in PRIORITY_QUERIES]; last_green_check = now
                if now - last_secondary_check > 1200:
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
                        
                        # Si c'est la première fois qu'on voit cette requête, on ne fait qu'initialiser
                        is_new_query = q_key not in initialized_queries
                        
                        for it in items:
                            if it['id'] not in seen_ids:
                                seen_ids.add(it['id'])
                                
                                # CRITÈRE D'ALERTE :
                                # 1. Recherche déjà initialisée au tour précédent
                                # 2. L'ID est strictement supérieur au dernier ID vu (sécurité temps)
                                # 3. Pas un article "Boosté" perdu au milieu (sauf si tout début de grid)
                                if not is_new_query and it['id'] > last_seen_id:
                                    if it['is_boosted'] and it['index'] > 2:
                                        # On ignore les vieux trucs boostés qui remontent
                                        continue
                                        
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
                log("⏳ Cycle terminé. Repos 10s...")
                time.sleep(10)

        except Exception as e:
            log(f"🚨 Bug global : {e}"); time.sleep(30)

if __name__ == "__main__":
    run_bot()
