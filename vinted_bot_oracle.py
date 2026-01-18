#!/usr/bin/env python3
"""
Vinted Bot V11.28 - SIMPLE STABLE RECOVERY
- Code épuré au maximum pour la stabilité
- Logs de décompte d'articles pour voir ce que le bot "voit" réellement
- Correction du sélecteur d'articles (grid-item)
- Signature Anti-Repost (Vendeur+Titre+Prix)
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
    # Ajout d'un cache-buster léger
    ts = int(time.time() / 15)
    url = f"https://www.vinted.fr/catalog?search_text={query.replace(' ', '+')}&order=newest_first&v={ts}"
    if color_id: url += f"&color_ids[]={color_id}"
    return url

def extract_items(page):
    try:
        # Attente d'un élément de grille ou de catalogue
        page.wait_for_selector('div[data-testid*="item"], div[class*="feed-grid__item"]', timeout=12000)
        return page.evaluate("""() => {
            const items = [];
            const elements = document.querySelectorAll('div[data-testid*="item"], div[class*="feed-grid__item"]');
            elements.forEach(el => {
                const a = el.querySelector('a');
                if (!a) return;
                const url = a.href;
                const idMatch = url.match(/items\\/(\\d+)/);
                if (!idMatch) return;
                const id = parseInt(idMatch[1]);
                
                const title = a.getAttribute('title') || "Maillot ASSE";
                const sellerEl = el.querySelector('h4, span[class*="seller"], [data-testid*="seller-name"]');
                const seller = sellerEl ? sellerEl.innerText.trim() : "Inconnu";
                
                const priceEl = el.querySelector('h3, [class*="price"], [data-testid*="price"]');
                let price = priceEl ? priceEl.innerText.trim().split('\\n')[0] : "N/A";
                
                const photo = el.querySelector('img')?.src || "";
                
                items.push({
                    id: id, url: url, title: title, seller: seller, 
                    price: price, photo: photo,
                    signature: seller + "_" + title + "_" + price
                });
            });
            return items;
        }""")
    except Exception as e:
        return []

def send_alert(context, item):
    if not DISCORD_WEBHOOK_URL: return
    try:
        p = context.new_page()
        p.goto(item['url'], wait_until='domcontentloaded', timeout=15000)
        time.sleep(1)
        photos = p.evaluate("() => Array.from(document.querySelectorAll('.item-photo--1 img, .item-photos img')).map(img => img.src).filter(s => s.includes('images.vinted'))")
        desc = p.evaluate("() => document.querySelector('[itemprop=\"description\"]')?.innerText || ''")
        p.close()
        
        payload = {
            "content": f"@everyone | {item['title']}\n💰 {item['price']} | 👤 {item['seller']}",
            "embeds": [{
                "title": f"🔔 {item['title']}", "url": item['url'], "color": 0x09B83E,
                "description": f"**{item['price']}**\n\n{desc[:300]}...",
                "image": {"url": photos[0] if photos else item['photo']},
                "footer": {"text": "Vinted Sniper V11.28"},
                "timestamp": datetime.utcnow().isoformat() + "Z"
            }]
        }
        requests.post(DISCORD_WEBHOOK_URL, json=payload, timeout=10)
        log(f"✅ Alerte envoyée : {item['title']} (#{item['id']})")
    except: pass

def run_bot():
    log("🚀 Démarrage V11.28 (SIMPLE & STABLE)")
    last_id = load_last_seen_id()
    sent_signatures = load_json(SIGNATURES_FILE, [])
    
    seen_ids = set()
    last_green_check = 0
    last_secondary_check = 0
    
    # Premier cycle silencieux pour caler l'ID de référence
    is_initial_cycle = True
    log(f"🎯 Référence actuelle : ID {last_id}")

    while True:
        try:
            gc.collect()
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True, args=['--no-sandbox', '--disable-dev-shm-usage'])
                context = browser.new_context(
                    user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                    locale='fr-FR'
                )
                
                # Bloquer les ressources lourdes pour économiser Railway
                def block(route):
                    if route.request.resource_type in ["image", "stylesheet", "font", "media"]: route.abort()
                    else: route.continue_()
                context.route("**/*", block)

                now = time.time()
                queries = [(q, None) for q in PRIORITY_QUERIES]
                if now - last_green_check > 300:
                    queries += [(q, 10) for q in PRIORITY_QUERIES]; last_green_check = now
                if now - last_secondary_check > 1200:
                    queries += [(q, None) for q in SECONDARY_QUERIES]; last_secondary_check = now
                
                cycle_max_id = last_id
                
                for q, c in queries:
                    try:
                        log(f"🔎 Check: {q}{' [VERT]' if c else ''}")
                        page = context.new_page()
                        page.goto(get_search_url(q, c), wait_until='domcontentloaded', timeout=25000)
                        
                        # Vérification du blocage
                        title = page.title()
                        if "Vinted" not in title and "Articles" not in title:
                            log(f"   ⚠️ Block probable (Titre: {title})")
                            page.close(); continue
                            
                        items = extract_items(page)
                        log(f"   ∟ {len(items)} articles vus")
                        
                        for it in items:
                            if it['id'] in seen_ids: continue
                            seen_ids.add(it['id'])
                            
                            if it['id'] > last_id:
                                if it['id'] > cycle_max_id: cycle_max_id = it['id']
                                
                                if is_initial_cycle: continue
                                if it['signature'] in sent_signatures: continue
                                
                                # Filtres ASSE un peu plus larges
                                t = it['title'].lower()
                                keywords = ["asse", "saint-etienne", "saint etienne", "st etienne", "sainté", "vert"]
                                if any(k in t for k in keywords) or c == 10:
                                    send_alert(context, it)
                                    sent_signatures.append(it['signature'])
                                    if len(sent_signatures) > 3000: sent_signatures.pop(0)
                                    save_json(SIGNATURES_FILE, sent_signatures)
                        
                        page.close()
                    except Exception as e:
                        # log(f"   ⚠️ Erreur sur {q}: {e}")
                        pass
                
                browser.close()
                is_initial_cycle = False # Fin du premier cycle silencieux
                
                if cycle_max_id > last_id:
                    last_id = cycle_max_id
                    with open(STATE_FILE, "w") as f: f.write(str(last_id))

                log("⏳ Cycle terminé. Repos 10s...")
                time.sleep(10)

        except Exception as e:
            log(f"🚨 Erreur globale : {e}"); time.sleep(20)

if __name__ == "__main__":
    run_bot()
