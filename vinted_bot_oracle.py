#!/usr/bin/env python3
"""
Vinted Bot V11.15 - EXACT NICKEL RESTORE
- Retour aux réglages V10.6 (Semaine dernière)
- Blocage TOUT (Images, CSS, Fonts, Media)
- Repos 10 secondes (Sniper Mode)
- Alertes Premium V10.2 conservées
"""

import os
import sys
import time
import random
import requests
import signal
import gc
from datetime import datetime
from playwright.sync_api import sync_playwright

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
    if color_id: url += f"&color_ids[]={color_id}"
    return url

def scrape_item_details(context, item_url):
    """Extraction robuste des détails"""
    page = None
    try:
        page = context.new_page()
        # On attend pas le chargement complet pour sauver de la RAM
        page.goto(item_url, wait_until='domcontentloaded', timeout=15000)
        
        # On attend 1s que le JS s'installe
        time.sleep(1)

        # Extraction Photos (Indispensable)
        photos = page.evaluate("""() => {
            const imgs = Array.from(document.querySelectorAll('.item-photo--1 img, .item-photos img'));
            return imgs.map(img => img.src).filter(src => src && src.includes('images.vinted'));
        }""")
        
        # Description et Attributs (Scraping DOM direct)
        data = page.evaluate("""() => {
            return {
                description: document.querySelector('[itemprop="description"]')?.innerText || "",
                brand: document.querySelector('.item-attributes [itemprop="brand"]')?.innerText || "N/A",
                size: document.querySelector('.item-attributes [itemprop="size"]')?.innerText || "N/A",
                status: document.querySelector('.item-attributes [itemprop="itemCondition"]')?.innerText || "N/A"
            };
        }""")
        return {
            "description": data['description'],
            "photos": photos,
            "brand": data['brand'],
            "size": data['size'],
            "status": data['status']
        }
    except:
        return {"description": "", "photos": [], "brand": "N/A", "size": "N/A", "status": "N/A"}
    finally:
        if page: page.close()

def extract_items_from_page(page):
    try:
        return page.evaluate("""() => {
            const items = [];
            const elements = document.querySelectorAll('div[data-testid*="item"]');
            elements.forEach((el) => {
                const a = el.querySelector('a');
                if (!a) return;
                const idMatch = a.href.match(/items\\/(\\d+)/);
                if (!idMatch) return;
                const priceMatch = el.innerText.match(/\\d+[.,]\\d+\\s*[$€]/);
                items.push({
                    id: parseInt(idMatch[1]), 
                    url: a.href, 
                    title: a.getAttribute('title') || "Maillot ASSE",
                    price: priceMatch ? priceMatch[0] : 'N/A'
                });
            });
            return items;
        }""")
    except: return []

def send_discord_alert(context, item):
    if not DISCORD_WEBHOOK_URL: return
    try:
        d = scrape_item_details(context, item['url'])
        f_desc = clean_text(d['description'])
        desc_preview = f_desc[:1000] + "..." if len(f_desc) > 1000 else (f_desc if f_desc else "Pas de description")
        
        import re
        clean_title = item['title'].split(',')[0].split('·')[0].strip()
        clean_title = re.sub(r'\\d+[.,]\\d+\\s*€.*$', '', clean_title).strip()
        if not clean_title: clean_title = "Maillot ASSE"

        payload = {
            "content": f"@everyone | {clean_title}\n💰 {item['price']} | 📏 {d['size']} | 🏷️ {d['brand']}\n📝 {desc_preview}",
            "username": "Vinted ASSE Bot",
            "avatar_url": "https://images.vinted.net/assets/icon-76x76-precomposed-3e6e4c5f0b8c7e5a5c5e5e5e5e5e5e5e.png",
            "embeds": [{
                "title": f"🔔 {clean_title}", "url": item['url'], "color": 0x09B83E,
                "description": f"**{item['price']}** | Taille: **{d['size']}**\nMarque: **{d['brand']}**\nÉtat: {d['status']}\n\n{f_desc[:300]}...",
                "image": {"url": d['photos'][0] if d['photos'] else ""},
                "footer": {"text": f"Vinted Bot • ID: {item['id']}"},
                "timestamp": datetime.utcnow().isoformat() + "Z"
            }]
        }
        requests.post(DISCORD_WEBHOOK_URL, json=payload, timeout=10)
        log(f"✅ Alerte envoyée #{item['id']}")
    except Exception as e:
        log(f"❌ Erreur alerte: {e}")

def run_bot():
    log("🚀 RESTAURATION VERSION NICKEL (V11.15)")
    seen_ids = set()
    initialized_queries = set()
    last_green_check = 0
    last_secondary_check = 0
    last_seen_id = load_last_seen_id()

    while True:
        try:
            gc.collect()
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True, args=['--no-sandbox', '--disable-dev-shm-usage', '--disable-gpu'])
                context = browser.new_context(user_agent="Mozilla/5.0", locale="fr-FR")
                
                # BLOCAGE TOTAL POUR ÉCONOMISER RAM & CPU (Version Nickel)
                def block(route):
                    if route.request.resource_type in ["image", "stylesheet", "font", "media"]:
                        route.abort()
                    else:
                        route.continue_()
                context.route("**/*", block)

                now = time.time()
                queries = [(q, None) for q in PRIORITY_QUERIES]
                if now - last_green_check > 300:
                    queries += [(q, 10) for q in PRIORITY_QUERIES]; last_green_check = now
                if now - last_secondary_check > 900:
                    queries += [(q, None) for q in SECONDARY_QUERIES]; last_secondary_check = now

                for q, c in queries:
                    q_key = f"{q}_{c}"
                    page = None
                    try:
                        page = context.new_page()
                        page.goto(get_search_url(q, c), wait_until="domcontentloaded", timeout=25000)
                        items = extract_items_from_page(page)
                        
                        is_new = q_key not in initialized_queries
                        for it in items:
                            if it['id'] not in seen_ids:
                                seen_ids.add(it['id'])
                                if not is_new and it['id'] > last_seen_id:
                                    t = it['title'].lower()
                                    if any(k in t for k in ["asse", "saint", "sainte", "st-"]) and \
                                       (any(k in t for k in ["maillot", "jersey", "trikot", "ensemble"]) or c == 10):
                                        send_discord_alert(context, it)
                                        last_seen_id = max(last_seen_id, it['id']); save_last_seen_id(last_seen_id)
                        initialized_queries.add(q_key)
                        page.close()
                    except:
                        if page: page.close()

                browser.close()
            
            # Nettoyage cache pour RAM
            if len(seen_ids) > 1500:
                seen_ids = set(sorted(list(seen_ids), reverse=True)[:1000])

            log("⏳ Sniper en attente (repos 10s)...")
            time.sleep(10) # 10 secondes comme avant
            
        except Exception as e:
            log(f"🚨 Bug global : {e}"); time.sleep(20)

if __name__ == "__main__":
    run_bot()
