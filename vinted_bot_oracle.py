#!/usr/bin/env python3
"""
Vinted Bot V10.6 "NICKEL" - DOUBLE SECURITY
- Retour exact au moteur V10.6
- Sécurité renforcée contre les alertes multiples (Compare IDs strictement)
- Instance Logging pour diagnostic
"""

import os
import sys
import time
import random
import requests
import signal
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

def extract_items_from_page(page):
    try:
        page.wait_for_selector('div[data-testid*="item"]', timeout=10000)
        return page.evaluate("""() => {
            const items = [];
            document.querySelectorAll('div[data-testid*="item"]').forEach(el => {
                const a = el.querySelector('a');
                if (!a) return;
                const url = a.href;
                const id = parseInt(url.match(/items\\/(\\d+)/)?.[1] || 0);
                if (!id) return;
                const title = a.getAttribute('title') || "Maillot ASSE";
                const sellerEl = el.querySelector('h4, [class*="seller"]');
                const seller = sellerEl ? sellerEl.innerText.trim() : "Inconnu";
                const texts = Array.from(el.querySelectorAll('p, span, h3')).map(e => e.innerText);
                const price = texts.find(t => t.includes('€')) || "N/A";
                items.push({ id: id, url: url, title: title, seller: seller, price: price, photo: el.querySelector('img')?.src || "" });
            });
            return items;
        }""")
    except: return []

def send_alert(context, item):
    if not DISCORD_WEBHOOK_URL: return
    try:
        p = context.new_page()
        p.goto(item['url'], wait_until='domcontentloaded', timeout=15000)
        time.sleep(1)
        photos = p.evaluate("() => Array.from(document.querySelectorAll('.item-photo--1 img')).map(img => img.src)")
        desc = p.evaluate("() => document.querySelector('[itemprop=\"description\"]')?.innerText || ''")
        p.close()
        
        payload = {
            "content": f"@everyone | {item['title']}\n💰 {item['price']} | 👤 {item['seller']}",
            "embeds": [{
                "title": f"🔔 {item['title']}", "url": item['url'], "color": 0x09B83E,
                "description": f"**{item['price']}**\n\n{desc[:300]}...",
                "image": {"url": photos[0] if photos else item['photo']},
                "footer": {"text": "Vinted Sniper V10.6 Stable"}
            }]
        }
        requests.post(DISCORD_WEBHOOK_URL, json=payload, timeout=10)
        log(f"✅ Alerte envoyée : {item['title']} (#{item['id']})")
    except: pass

def run_bot():
    instance_id = random.randint(1000, 9999)
    log(f"🚀 Démarrage Instance #{instance_id} (V10.6 NICKEL)")
    
    seen_ids = set()
    last_green_check = 0
    last_secondary_check = 0
    is_initial_cycle = True
    
    while True:
        last_seen_id = load_last_seen_id()
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True, args=['--no-sandbox'])
                context = browser.new_context(user_agent='Mozilla/5.0')
                
                def block(route):
                    if route.request.resource_type in ["image", "stylesheet", "font", "media"]: route.abort()
                    else: route.continue_()
                context.route("**/*", block)

                now = time.time()
                queries = [(q, None) for q in PRIORITY_QUERIES]
                if now - last_green_check > 300:
                    for q in PRIORITY_QUERIES: queries.append((q, 10)); last_green_check = now
                if now - last_secondary_check > 1200:
                    for q in SECONDARY_QUERIES: queries.append((q, None)); last_secondary_check = now

                cycle_max_id = last_seen_id

                for q, color in queries:
                    try:
                        page = context.new_page()
                        page.goto(f"https://www.vinted.fr/catalog?search_text={q.replace(' ', '+')}&order=newest_first" + (f"&color_ids[]={color}" if color else ""), timeout=25000)
                        items = extract_items_from_page(page)
                        
                        for it in items:
                            if it['id'] in seen_ids: continue
                            seen_ids.add(it['id'])
                            
                            # SÉCURITÉ ANTI-TRIPLE : On compare strictement au dernier ID sauvé
                            if it['id'] > last_seen_id:
                                if it['id'] > cycle_max_id: cycle_max_id = it['id']
                                
                                # Si ce n'est pas le tour de chauffe, on alerte
                                if not is_initial_cycle:
                                    t = it['title'].lower()
                                    if any(k in t for k in ["asse", "saint-etienne", "st etienne", "sainté"]) or color == 10:
                                        send_alert(context, it)
                        page.close()
                    except: pass
                
                browser.close()
                is_initial_cycle = False
                
                if cycle_max_id > last_seen_id:
                    save_last_seen_id(cycle_max_id)

                log(f"⏳ Cycle Instance #{instance_id} terminé. Repos 10s...")
                time.sleep(10)

        except Exception as e:
            log(f"🚨 Erreur : {e}"); time.sleep(20)

if __name__ == "__main__":
    run_bot()
