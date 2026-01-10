#!/usr/bin/env python3
"""
Vinted Bot V11.6 - FULL CONTENT SNIPER
- Restauration de l'analyse intelligente des titres (Brand, Size, Status)
- Sécurité anti N/A (Fallback systématique)
- Single Page Sniper & Green Energy (Optimisation budget conservée)
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
        page.goto(item_url, wait_until='domcontentloaded', timeout=15000)
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
    except: pass
    return {"description": "", "photos": [], "brand": "N/A", "size": "N/A", "status": "N/A"}

def extract_items_from_page(page):
    try:
        return page.evaluate("""() => {
            const items = [];
            const els = document.querySelectorAll('div[data-testid*="item"]');
            els.forEach(el => {
                const a = el.querySelector('a');
                if (!a) return;
                const url = a.href;
                const idMatch = url.match(/items\\/(\\d+)/);
                if (!idMatch) return;
                const id = parseInt(idMatch[1]);
                
                const rawTitle = a.getAttribute('title') || '';
                const img = el.querySelector('img');
                const priceMatch = el.innerText.match(/\\d+[.,]\\d+\\s*[$€]/);
                
                // PARSING INTELLIGENT DU TITRE (V6.0)
                let brand = 'N/A';
                let size = 'N/A';
                let status = 'N/A';
                if (rawTitle.includes('marque:') || rawTitle.includes('taille:')) {
                    const bM = rawTitle.match(/marque:\\s*([^,]+)/i);
                    if (bM) brand = bM[1].trim();
                    const sM = rawTitle.match(/taille:\\s*([^,]+)/i);
                    if (sM) size = sM[1].trim();
                    const stM = rawTitle.match(/état:\\s*([^,]+)/i);
                    if (stM) status = stM[1].trim();
                }

                items.push({
                    id: id,
                    url: url,
                    raw_title: rawTitle,
                    photo: img?.src || '',
                    price: priceMatch ? priceMatch[0] : 'N/A',
                    brand: brand,
                    size: size,
                    status: status
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
        
        # FALLBACK : On utilise les infos du titre si les détails API ont échoué
        f_brand = d['brand'] if d['brand'] != 'N/A' else item['brand']
        f_size = d['size'] if d['size'] != 'N/A' else item['size']
        f_status = d['status'] if d['status'] != 'N/A' else item['status']
        final_desc = clean_text(d['description'])
        
        # Nettoyage Titre (Version Ultra-Propre)
        import re
        t = item['raw_title']
        clean_title = t.split(',')[0].split('·')[0].strip()
        clean_title = re.sub(r'\\d+[.,]\\d+\\s*€.*$', '', clean_title).strip()
        if not clean_title or len(clean_title) < 3: clean_title = "Maillot ASSE"

        desc_preview = final_desc[:1000] + "..." if len(final_desc) > 1000 else (final_desc if final_desc else "Pas de description")
        
        payload = {
            "content": f"@everyone | {clean_title}\n💰 {item['price']} | 📏 {f_size} | 🏷️ {f_brand}\n📝 {desc_preview}",
            "username": "Vinted ASSE Bot",
            "avatar_url": "https://images.vinted.net/assets/icon-76x76-precomposed-3e6e4c5f0b8c7e5a5c5e5e5e5e5e5e5e.png", 
            "embeds": [{
                "title": f"🔔 {clean_title}",
                "url": item['url'],
                "color": 0x09B83E,
                "description": f"**{item['price']}** | Taille: **{f_size}**\nMarque: **{f_brand}**\nÉtat: {f_status}\n\n{final_desc[:300]}...",
                "image": {"url": d['photos'][0] if d['photos'] else item['photo']},
                "timestamp": datetime.utcnow().isoformat() + "Z",
                "footer": {"text": f"Vinted Bot • ID: {item['id']}"}
            }]
        }
        requests.post(DISCORD_WEBHOOK_URL, json=payload, timeout=10)
        log(f"✅ Alerte envoyée #{item['id']}")
    except Exception as e:
        log(f"❌ Erreur alerte: {e}")

def watchdog_handler(signum, frame):
    log("🚨 WATCHDOG: Redémarrage forcé !")
    os._exit(1)

def run_bot():
    log("🚀 Démarrage SNIPER V11.6 - FULL CONTENT")
    seen_ids = set()
    last_green_check = 0
    last_secondary_check = 0
    last_seen_id = load_last_seen_id()
    is_initial = True
    cycle_count = 0

    while True:
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True, args=['--no-sandbox'])
                ua = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
                context = browser.new_context(user_agent=ua, locale='fr-FR')
                
                # ENERGY OPTIMIZATION
                def block(route):
                    if route.request.resource_type in ["image", "font", "media"]: route.abort()
                    else: route.continue_()
                context.route("**/*", block)

                search_page = context.new_page()

                while cycle_count < 20:
                    now = time.time()
                    hour = (datetime.utcnow().hour + 1) % 24
                    if 1 <= hour < 7:
                        log("🌙 Veille nuit..."); time.sleep(600); continue

                    queries = [(q, None) for q in PRIORITY_QUERIES]
                    if now - last_green_check > 300:
                        queries += [(q, 10) for q in PRIORITY_QUERIES]; last_green_check = now
                    if now - last_secondary_check > 1200:
                        queries += [(q, None) for q in SECONDARY_QUERIES]; last_secondary_check = now

                    log(f"🚀 Cycle {cycle_count}/20")
                    signal.signal(signal.SIGALRM, watchdog_handler)
                    signal.alarm(300)

                    for q, c in queries:
                        try:
                            log(f"🔎 Check: '{q}'{' [VERTE]' if c else ''}")
                            search_page.goto(get_search_url(q, c), wait_until="domcontentloaded", timeout=30000)
                            time.sleep(1)
                            search_page.wait_for_selector('div[data-testid*="item"]', timeout=15000)
                            
                            items = extract_items_from_page(search_page)
                            for it in items:
                                if it['id'] not in seen_ids:
                                    seen_ids.add(it['id'])
                                    if not is_initial and it['id'] > last_seen_id:
                                        t = it['raw_title'].lower()
                                        if any(k in t for k in ["asse", "saint", "st-", "sainté"]) and \
                                           (any(k in t for k in ["maillot", "jersey", "camiseta", "trikot"]) or c == 10):
                                            send_discord_alert(context, it)
                                            last_seen_id = max(last_seen_id, it['id']); save_last_seen_id(last_seen_id)
                            time.sleep(random.uniform(0.5, 1))
                        except Exception as e:
                            log(f"⚠️ Erreur {q}: {str(e)[:40]}")
                    
                    is_initial = False
                    cycle_count += 1
                    signal.alarm(0)
                    log(f"⏳ Repos 10s...")
                    time.sleep(10)

                browser.close()
                cycle_count = 0
                log("🔄 Refresh Navigateur...")
        except Exception as e:
            log(f"🚨 Bug global: {e}"); time.sleep(20)

if __name__ == "__main__":
    run_bot()
