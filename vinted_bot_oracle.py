#!/usr/bin/env python3
"""
Vinted Bot V11.25 - THE ANTI-BLOCK SNIPER
- Correction du blocage (Accept-Language + Stealth Headers)
- Retour à wait_until='domcontentloaded' pour la stabilité
- Fix du silence au démarrage (on garde l'ID de référence sans spammer)
- Signature Anti-Repost maintenue
"""

import os
import sys
import time
import random
import requests
import signal
import gc
import json
import re
from datetime import datetime
from playwright.sync_api import sync_playwright

# Configuration
PRIORITY_QUERIES = ["Maillot Asse", "Maillot Saint-Etienne", "Maillot St Etienne"]
SECONDARY_QUERIES = ["Jersey Asse", "Jersey Saint-Etienne", "Maglia Asse", "Camiseta Asse", "Ensemble Asse", "Trikot Asse"]
DISCORD_WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL")

STATE_FILE = "last_seen_id.txt"
SIGNATURES_FILE = "sent_signatures.json"

def log(message):
    timestamp = datetime.now().strftime('%H:%M:%S')
    print(f"[{timestamp}] {message}", flush=True)

def load_json(filename, default):
    if os.path.exists(filename):
        try:
            with open(filename, "r") as f: return json.load(f)
        except: pass
    return default

def save_json(filename, data):
    try:
        with open(filename, "w") as f: json.dump(data, f)
    except: pass

def load_last_seen_id():
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r") as f:
                val = int(f.read().strip())
                return val
        except: pass
    return 0

def get_search_url(query, color_id=None):
    # Bypass cache léger
    ts = int(time.time() / 10) # Change toutes les 10s seulement
    url = f"https://www.vinted.fr/catalog?search_text={query.replace(' ', '+')}&order=newest_first&v={ts}"
    if color_id: url += f"&color_ids[]={color_id}"
    return url

def extract_items_from_page(page):
    try:
        # Attente selector avec timeout raisonnable
        page.wait_for_selector('div[data-testid*="item"]', timeout=10000)
        return page.evaluate("""
            () => {
                const items = [];
                const itemElements = document.querySelectorAll('div[data-testid*="item"]');
                
                itemElements.forEach((el) => {
                    try {
                        const link = el.querySelector('a');
                        if (!link) return;
                        const url = link.href;
                        const idMatch = url.match(/items\\/(\\d+)/);
                        if (!idMatch) return;
                        const itemId = parseInt(idMatch[1]);
                        
                        const sellerEl = el.querySelector('[data-testid*="seller-name"], h4, span[class*="seller"]');
                        const seller = sellerEl ? sellerEl.innerText.trim() : "Inconnu";
                        
                        const priceEl = el.querySelector('[data-testid*="price"], h3, [class*="price"]');
                        let price = priceEl ? priceEl.innerText.trim() : "N/A";
                        if (price.includes('\\n')) price = price.split('\\n')[0];

                        const title = link.getAttribute('title') || "Maillot ASSE";
                        const photo = el.querySelector('img')?.src || '';
                        
                        items.push({
                            id: itemId, title: title, price: price, url: url, photo: photo, 
                            seller: seller,
                            signature: btoa(unescape(encodeURIComponent(seller + "_" + title + "_" + price)))
                        });
                    } catch (e) {}
                });
                return items;
            }
        """)
    except:
        return []

def send_discord_alert(context, item):
    if not DISCORD_WEBHOOK_URL: return
    try:
        # Détails riches
        photos, desc = [item['photo']], "Nouveauté !"
        try:
            p = context.new_page()
            p.goto(item['url'], wait_until='domcontentloaded', timeout=12000)
            time.sleep(1)
            photos = p.evaluate("""() => Array.from(document.querySelectorAll('.item-photo--1 img, .item-photos img')).map(img => img.src).filter(src => src.includes('images.vinted'))""")
            desc = p.evaluate("() => document.querySelector('[itemprop=\"description\"]')?.innerText || ''")
            p.close()
        except: pass

        payload = {
            "content": f"@everyone | {item['title']}\n💰 {item['price']} | 👤 {item['seller']}",
            "embeds": [{
                "title": f"🔔 {item['title']}", "url": item['url'], "color": 0x09B83E,
                "description": f"**{item['price']}**\nVendeur : **{item['seller']}**\n\n{desc[:300]}...",
                "image": {"url": photos[0] if photos else item['photo']},
                "footer": {"text": f"Vinted Sniper V11.25"}
            }]
        }
        requests.post(DISCORD_WEBHOOK_URL, json=payload, timeout=10)
        log(f"   ✅ Alerte envoyée : {item['title']}")
    except: pass

def run_bot():
    log("🚀 Démarrage V11.25 ANTI-BLOCK")
    
    last_id = load_last_seen_id()
    sent_signatures = set(load_json(SIGNATURES_FILE, []))
    
    seen_ids = set()
    initialized_queries = set()
    last_green_check = 0
    last_secondary_check = 0

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=['--no-sandbox', '--disable-dev-shm-usage', '--disable-gpu'])
        
        # Contexte furtif
        context = browser.new_context(
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
            viewport={'width': 1280, 'height': 720},
            extra_http_headers={
                "Accept-Language": "fr-FR,fr;q=0.9,en-US;q=0.8,en;q=0.7",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
                "sec-ch-ua": '"Chromium";v="122", "Not(A:Brand";v="24", "Google Chrome";v="122"',
                "sec-ch-ua-mobile": "?0",
                "sec-ch-ua-platform": '"Windows"',
                "sec-fetch-dest": "document",
                "sec-fetch-mode": "navigate",
                "sec-fetch-site": "none",
                "sec-fetch-user": "?1",
                "upgrade-insecure-requests": "1"
            }
        )
        
        def block(route):
            if route.request.resource_type in ["image", "stylesheet", "font", "media"]: route.abort()
            else: route.continue_()
        context.route("**/*", block)

        log(f"🎯 Référence : ID {last_id}")

        try:
            while True:
                gc.collect()
                now = time.time()
                
                queries = [(q, None) for q in PRIORITY_QUERIES]
                if now - last_green_check > 300:
                    queries += [(q, 10) for q in PRIORITY_QUERIES]; last_green_check = now
                if now - last_secondary_check > 1200:
                    queries += [(q, None) for q in SECONDARY_QUERIES]; last_secondary_check = now

                cycle_max_id = last_id
                
                # Le premier cycle de chaque requête remplit juste l'ID sans sonner
                is_warming_up = (last_id == 0)

                for q, c in queries:
                    q_key = f"{q}_{c}"
                    try:
                        page = context.new_page()
                        # Navigation plus stable
                        page.goto(get_search_url(q, c), wait_until="domcontentloaded", timeout=25000)
                        items = extract_items_from_page(page)
                        
                        if not items:
                            log(f"   ⚠️ {q}: Rien détecté (Block ?)")
                            page.close(); continue
                        
                        log(f"   🔎 {q}: {len(items)} items")
                        
                        for it in items:
                            if it['id'] in seen_ids: continue
                            seen_ids.add(it['id'])

                            if it['id'] > last_id:
                                if it['id'] > cycle_max_id: cycle_max_id = it['id']

                                # On ne sonne pas au premier tour d'une nouvelle requête
                                if q_key not in initialized_queries: continue

                                # Anti-Repost
                                if it['signature'] in sent_signatures: continue
                                
                                # Keywords
                                low_t = it['title'].lower()
                                team_kw = ["asse", "saint etienne", "saint-etienne", "st etienne", "st-etienne", "sainté", "sainte", "as st", "as saint", "vert"]
                                wear_kw = ["maillot", "jersey", "maglia", "camiseta", "trikot", "ensemble", "reproduction"]
                                
                                if any(k in low_t for k in team_kw) and (any(k in low_t for k in wear_kw) or c == 10):
                                    send_discord_alert(context, it)
                                    sent_signatures.add(it['signature'])
                                    if len(sent_signatures) > 10000: sent_signatures.remove(next(iter(sent_signatures)))
                                    save_json(SIGNATURES_FILE, list(sent_signatures))

                        initialized_queries.add(q_key)
                        page.close()
                        time.sleep(random.uniform(1, 2))
                    except: pass

                if cycle_max_id > last_id:
                    last_id = cycle_max_id
                    with open(STATE_FILE, "w") as f: f.write(str(last_id))

                if len(seen_ids) > 2000:
                    ids_sorted = sorted(list(seen_ids), reverse=True)
                    seen_ids = set(ids_sorted[:1500])

                log(f"⏳ Repos 10s...")
                time.sleep(10)
        finally:
            browser.close()

if __name__ == "__main__":
    run_bot()
