#!/usr/bin/env python3
"""
Vinted Bot V11.27 - RETOUR AUX SOURCES (V10.6 NICKEL + ANTI-REPOST)
- Reprise du code EXACT de la version stable V10.6
- Ajout UNIQUE de la signature Anti-Repost (Vendeur+Titre+Prix)
- Cycle 10s / Pas de fioritures / Simplicité maximum
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

# --- CONFIGURATION (V10.6) ---
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
    url = f"https://www.vinted.fr/catalog?search_text={query.replace(' ', '+')}&order=newest_first"
    if color_id: url += f"&color_ids[]={color_id}"
    return url

# Moteur d'extraction V10.6 d'origine
def extract_items(page):
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
                const photo = el.querySelector('img')?.src || "";
                
                items.push({
                    id: id, url: url, title: title, seller: seller, 
                    price: price, photo: photo,
                    signature: seller + "_" + title + "_" + price
                });
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
                "footer": {"text": "Vinted Sniper V11.27"}
            }]
        }
        requests.post(DISCORD_WEBHOOK_URL, json=payload, timeout=10)
        log(f"✅ Alerte envoyée : {item['title']}")
    except: pass

def run_bot():
    log("🚀 Démarrage V11.27 (RETOUR NICKEL)")
    last_id = load_last_seen_id()
    sent_signatures = load_json(SIGNATURES_FILE, [])
    
    seen_ids = set()
    last_green_check = 0
    last_secondary_check = 0
    
    # Silence au démarrage (Comme la V10.6)
    is_initial_cycle = True

    while True:
        try:
            gc.collect()
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True, args=['--no-sandbox'])
                context = browser.new_context(user_agent='Mozilla/5.0')
                
                # Bloquer le superflu (V10.6 Nickel)
                def block(route):
                    if route.request.resource_type in ["image", "stylesheet", "font", "media"]: route.abort()
                    else: route.continue_()
                context.route("**/*", block)

                now = time.time()
                queries = [(q, None) for q in PRIORITY_QUERIES]
                if now - last_green_check > 300:
                    queries += [(q, 10) for q in PRIORITY_QUERIES]; last_green_check = now
                
                cycle_max_id = last_id
                
                for q, c in queries:
                    try:
                        log(f"🔎 Check: {q}")
                        page = context.new_page()
                        page.goto(get_search_url(q, c), timeout=25000)
                        items = extract_items(page)
                        
                        for it in items:
                            if it['id'] in seen_ids: continue
                            seen_ids.add(it['id'])
                            
                            if it['id'] > last_id:
                                if it['id'] > cycle_max_id: cycle_max_id = it['id']
                                
                                if is_initial_cycle: continue
                                if it['signature'] in sent_signatures: continue
                                
                                # Filtres simples ASSE
                                t = it['title'].lower()
                                if any(k in t for k in ["asse", "saint-etienne", "st etienne", "sainté", "vert"]) or c == 10:
                                    send_alert(context, it)
                                    sent_signatures.append(it['signature'])
                                    if len(sent_signatures) > 500: sent_signatures.pop(0)
                                    save_json(SIGNATURES_FILE, sent_signatures)
                        
                        page.close()
                    except: pass
                
                browser.close()
                is_initial_cycle = False
                
                if cycle_max_id > last_id:
                    last_id = cycle_max_id
                    with open(STATE_FILE, "w") as f: f.write(str(last_id))

                log("⏳ Cycle terminé. Repos 10s...")
                time.sleep(10)

        except Exception as e:
            log(f"🚨 Erreur : {e}"); time.sleep(20)

if __name__ == "__main__":
    run_bot()
