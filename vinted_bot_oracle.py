#!/usr/bin/env python3
"""
Vinted Bot V10.6 "NICKEL RESTORE"
- Version stable identifiée avant les modifications complexes
- 10s sleep cycle
- Blocage agressif des ressources (RAM/CPU optimized)
- Watchdog 180s actif
"""

import os
import sys
import time
import random
import requests
import signal
from datetime import datetime
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout

# Configuration des recherches
PRIORITY_QUERIES = ["Maillot Asse", "Maillot Saint-Etienne", "Maillot St Etienne"]
SECONDARY_QUERIES = ["Jersey Asse", "Jersey Saint-Etienne", "Maglia Asse", "Camiseta Asse", "Ensemble Asse", "Trikot Asse"]
SEARCH_QUERIES = PRIORITY_QUERIES + SECONDARY_QUERIES

DISCORD_WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL")
STATE_FILE = "last_seen_id.txt"

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

def log(message):
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    print(f"[{timestamp}] {message}", flush=True)

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

def scrape_item_details(page, item_url):
    try:
        import re
        id_match = re.search(r'/items/(\d+)', item_url)
        item_id = id_match.group(1) if id_match else None
        
        if not item_id:
            return {"description": "", "photos": [], "brand": "N/A", "size": "N/A", "status": "N/A"}

        page.goto(item_url, wait_until='domcontentloaded', timeout=15000)

        photos = page.evaluate("""() => {
            const imgs = Array.from(document.querySelectorAll('.item-photo--1 img, .item-photos img'));
            return imgs.map(img => img.src).filter(src => src);
        }""")
        photos = list(dict.fromkeys(photos))

        api_data = page.evaluate(f"""async () => {{
            try {{
                const response = await fetch('/api/v2/items/{item_id}?localize=false');
                return response.ok ? await response.json() : null;
            }} catch (e) {{ return null; }}
        }}""")
        
        brand, size, status, description = "N/A", "N/A", "N/A", ""
        if api_data and 'item' in api_data:
            it = api_data['item']
            description = it.get('description', '')
            brand = it.get('brand_title', 'N/A')
            size = it.get('size_title', 'N/A')
            status = it.get('status', 'N/A')
        else:
            description = page.evaluate("() => document.querySelector('[itemprop=\"description\"]')?.innerText || ''")
        
        return {"description": description, "photos": photos, "brand": brand, "size": size, "status": status}
    except Exception as e:
        log(f"⚠️ Erreur détails: {e}")
        return {"description": "", "photos": [], "brand": "N/A", "size": "N/A", "status": "N/A"}

def extract_items_from_page(page):
    try:
        page.wait_for_selector('div[data-testid*="item"]', timeout=10000)
        time.sleep(random.uniform(1, 2))
        return page.evaluate("""
            () => {
                const items = [];
                const itemElements = document.querySelectorAll('div[data-testid*="item"], div[class*="feed-grid__item"]');
                itemElements.forEach((el) => {
                    try {
                        const link = el.querySelector('a');
                        if (!link) return;
                        const url = link.href;
                        const idMatch = url.match(/items\\/(\\d+)/);
                        if (!idMatch) return;
                        const itemId = parseInt(idMatch[1]);
                        
                        let rawTitle = link.getAttribute('title') || el.querySelector('img')?.alt || '';
                        let price = 'N/A', size = 'N/A', brand = 'N/A', status = 'Non spécifié';
                        let title = rawTitle;

                        if (rawTitle.includes('marque:') || rawTitle.includes('taille:')) {
                            title = rawTitle.split(',')[0].trim();
                            const b = rawTitle.match(/marque:\\s*([^,]+)/i); if (b) brand = b[1].trim();
                            const s = rawTitle.match(/taille:\\s*([^,]+)/i); if (s) size = s[1].trim();
                            const st = rawTitle.match(/état:\\s*([^,]+)/i); if (st) status = st[1].trim();
                        }
                        
                        const texts = Array.from(el.querySelectorAll('p, h3, h4, span, div')).map(e => e.innerText.trim()).filter(t => t);
                        price = texts.find(t => t.includes('€') || t.includes('$')) || 'N/A';
                        
                        if (size === 'N/A') {
                            const sizeRegex = /^(XS|S|M|L|XL|XXL|\\d{2,3}|Unique)$/i;
                            size = texts.find(t => sizeRegex.test(t) && !t.includes('€')) || 'N/A';
                        }
                        
                        title = title.replace(/enlevé|nouveau|!/gi, '').trim();
                        if (!title) title = 'Maillot ASSE';
                        
                        items.push({ id: itemId, title: title, price: price, size: size, brand: brand, status: status, url: url, photo: el.querySelector('img')?.src || '' });
                    } catch (e) {}
                });
                return items;
            }
        """)
    except: return []

def send_discord_alert(context, item):
    if not DISCORD_WEBHOOK_URL: return
    try:
        detail_page = context.new_page()
        details = scrape_item_details(detail_page, item['url'])
        detail_page.close()

        brand = details['brand'] if details['brand'] != 'N/A' else item['brand']
        size = details['size'] if details['size'] != 'N/A' else item['size']
        desc = clean_text(details['description'])
        
        photos = details['photos'] if details['photos'] else ([item['photo']] if item['photo'] else [])
        
        payload = {
            "content": f"@everyone | {clean_text(item['title'])}\n💰 {clean_text(item['price'])} | 📏 {clean_text(size)} | 🏷️ {clean_text(brand)}\n📝 {desc[:1000]}",
            "username": "Vinted ASSE Bot",
            "embeds": [{
                "title": f"🔔 {clean_text(item['title'])}",
                "url": item['url'],
                "description": f"**{clean_text(item['price'])}** | Taille: **{clean_text(size)}**\nMarque: **{clean_text(brand)}**\n\n{desc[:300]}...",
                "color": 0x09B83E,
                "image": {"url": photos[0] if photos else ""},
                "footer": {"text": f"Vinted Bot • ID: {item['id']}"},
                "timestamp": datetime.utcnow().isoformat() + 'Z'
            }]
        }
        requests.post(DISCORD_WEBHOOK_URL, json=payload, timeout=10)
        log(f"✅ Alerte envoyée #{item['id']}")
    except Exception as e: log(f"❌ Erreur Discord: {e}")

def watchdog_handler(signum, frame):
    log("🚨 WATCHDOG: Bot figé ! Redémarrage...")
    os._exit(1)

def run_bot():
    log("🚀 Restauration Version stable V10.6 NICKEL")
    seen_ids = set()
    last_secondary_check = 0
    last_green_check = 0
    is_initial_cycle = True
    last_seen_id = load_last_seen_id()

    try:
        while True:
            import datetime as dt
            current_hour = (dt.datetime.utcnow().hour + 1) % 24
            if 1 <= current_hour < 7:
                log(f"🌙 Veille ({current_hour}h).")
                time.sleep(600)
                continue

            try:
                signal.signal(signal.SIGALRM, watchdog_handler)
                signal.alarm(180) 

                with sync_playwright() as p:
                    browser = p.chromium.launch(headless=True, args=['--no-sandbox', '--disable-dev-shm-usage', '--disable-gpu'])
                    context = browser.new_context(user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36', viewport={'width': 1280, 'height': 720}, locale='fr-FR')

                    def block(route):
                        if route.request.resource_type in ["image", "stylesheet", "font", "media"]: route.abort()
                        else: route.continue_()
                    context.route("**/*", block)

                    now = time.time()
                    queries_to_run = [(q, None) for q in PRIORITY_QUERIES]
                    if (now - last_green_check) > 300:
                        for q in PRIORITY_QUERIES: queries_to_run.append((q, 10))
                        last_green_check = now
                    if (now - last_secondary_check) > 1200:
                        for q in SECONDARY_QUERIES: queries_to_run.append((q, None))
                        last_secondary_check = now

                    log(f"⚡ Scan V10.6 : {len(queries_to_run)} requêtes")

                    for q, color in queries_to_run:
                        try:
                            page = context.new_page()
                            log(f"🔎 Check: '{q}'{' [VERT]' if color else ''}")
                            page.goto(get_search_url(q, color), wait_until='commit', timeout=20000)
                            items = extract_items_from_page(page)
                            
                            if items:
                                new_found = [it for it in items if it['id'] not in seen_ids and it['id'] > (last_seen_id - 100000)]
                                for it in new_found: seen_ids.add(it['id'])
                                
                                if is_initial_cycle:
                                    if new_found: last_seen_id = max(last_seen_id, max(x['id'] for x in new_found))
                                elif new_found:
                                    new_found.sort(key=lambda x: x['id'])
                                    for it in new_found:
                                        t_low = it['title'].lower()
                                        has_team = any(x in t_low for x in ["asse", "saint etienne", "st etienne", "sainté"])
                                        has_item = any(s in t_low for s in ["maillot", "jersey", "maglia", "camiseta", "ensemble", "trikot"])
                                        if (has_item and has_team) or (color == 10 and has_team):
                                            send_discord_alert(context, it)
                                    last_seen_id = max(last_seen_id, max(x['id'] for x in new_found))
                                    save_last_seen_id(last_seen_id)
                            page.close()
                            time.sleep(random.uniform(1, 2))
                        except Exception as e: log(f"⚠️ Erreur {q}: {e}")
                    
                    browser.close()
                signal.alarm(0)
            except Exception as e: log(f"🚨 Bug : {e}")

            is_initial_cycle = False
            if len(seen_ids) > 2000:
                seen_ids = set(sorted(list(seen_ids), reverse=True)[:1500])
            
            log(f"⏳ Cycle terminé. Repos 10s...")
            time.sleep(10)
    except KeyboardInterrupt: pass

if __name__ == "__main__":
    run_bot()
