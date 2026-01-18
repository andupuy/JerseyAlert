#!/usr/bin/env python3
"""
Vinted Bot V11.26 - ULTIMATE STEALTH RECOVERY
- Evasion avancée (navigator.webdriver bypass)
- Navigation organique (Home -> Search)
- Correction "Silence au démarrage" (on capture l'ID au 1er tour sans spammer)
- Headers 100% identiques à un Chrome Windows récent
- Sélection d'articles par sélecteurs multiples
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
            with open(STATE_FILE, "r") as f: return int(f.read().strip())
        except: pass
    return 0

def get_search_url(query, color_id=None):
    ts = int(time.time() / 15)
    url = f"https://www.vinted.fr/catalog?search_text={query.replace(' ', '+')}&order=newest_first&v={ts}"
    if color_id: url += f"&color_ids[]={color_id}"
    return url

def extract_items_from_page(page):
    try:
        # Attente selector multiple (Vinted change souvent)
        selectors = ['div[data-testid="grid-item"]', 'div[data-testid*="item"]', 'div[class*="feed-grid__item"]']
        found = False
        for sel in selectors:
             try:
                 page.wait_for_selector(sel, timeout=7000)
                 found = True
                 break
             except: continue
        
        if not found: return []

        return page.evaluate("""
            () => {
                const items = [];
                const itemElements = document.querySelectorAll('div[data-testid="grid-item"], div[class*="feed-grid__item"]');
                
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
        photos, desc = [item['photo']], "Nouveauté !"
        try:
            p = context.new_page()
            p.goto(item['url'], wait_until='domcontentloaded', timeout=15000)
            time.sleep(1.5)
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
                "footer": {"text": f"Vinted Sniper V11.26"}
            }]
        }
        requests.post(DISCORD_WEBHOOK_URL, json=payload, timeout=10)
        log(f"   ✅ Alerte envoyée : {item['title']}")
    except: pass

def run_bot():
    log("🚀 Démarrage V11.26 ULTRA-STEALTH")
    
    last_id = load_last_seen_id()
    sent_signatures = set(load_json(SIGNATURES_FILE, []))
    
    seen_ids = set()
    initialized_queries = set()
    last_green_check = 0
    last_secondary_check = 0

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=[
            '--no-sandbox', 
            '--disable-setuid-sandbox', 
            '--disable-dev-shm-usage', 
            '--disable-blink-features=AutomationControlled',
            '--disable-gpu'
        ])
        
        # Contexte ultra-réaliste
        context = browser.new_context(
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
            viewport={'width': 1280, 'height': 720},
            locale='fr-FR',
            extra_http_headers={
                "Accept-Language": "fr-FR,fr;q=0.9,en-US;q=0.8,en;q=0.7",
                "Connection": "keep-alive",
                "Upgrade-Insecure-Requests": "1"
            }
        )
        
        # Bypass navigator.webdriver
        context.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")

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
                
                for q, c in queries:
                    q_key = f"{q}_{c}"
                    try:
                        page = context.new_page()
                        
                        # ANTI-DETECTION : On passe par la home une fois sur 5
                        if random.random() < 0.2:
                             page.goto("https://www.vinted.fr", wait_until="domcontentloaded", timeout=20000)
                             time.sleep(random.uniform(1, 2))
                        
                        # Navigation vers la recherche
                        page.goto(get_search_url(q, c), wait_until="domcontentloaded", timeout=25000)
                        items = extract_items_from_page(page)
                        
                        if not items:
                            # Verification si c'est une page de block
                            if "Articles" not in page.title():
                                log(f"   ⚠️ Blocage détecté sur '{q}' (Titre: {page.title()})")
                            else:
                                log(f"   🔎 '{q}': Aucun item (Grid vide)")
                            page.close()
                            time.sleep(random.uniform(2, 5))
                            continue
                        
                        log(f"   🔎 {q}: {len(items)} items")
                        
                        for it in items:
                            if it['id'] in seen_ids: continue
                            seen_ids.add(it['id'])

                            if it['id'] > last_id:
                                if it['id'] > cycle_max_id: cycle_max_id = it['id']

                                # Silence intelligent : on note l'ID mais on ne sonne pas au 1er cycle de CHAQUE requête
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
                        time.sleep(random.uniform(1, 3))
                    except: pass

                if cycle_max_id > last_id:
                    last_id = cycle_max_id
                    with open(STATE_FILE, "w") as f: f.write(str(last_id))

                if len(seen_ids) > 2000:
                    ids_sorted = sorted(list(seen_ids), reverse=True)
                    seen_ids = set(ids_sorted[:1500])

                log("⏳ Repos 10s...")
                time.sleep(10)
        finally:
            browser.close()

if __name__ == "__main__":
    run_bot()
