#!/usr/bin/env python3
"""
Vinted Bot V11.18 - FULL AUTO ANTI-REPOST
- Signature automatique (Vendeur + Titre + Prix)
- Historique persistant pour éviter les doublons (sent_signatures.json)
- Zéro action manuelle requise
- Moteur Sniper V10.6 maintenu avec détection élargie
"""

import os
import sys
import time
import random
import requests
import signal
import gc
import json
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

def scrape_item_details(page, item_url):
    try:
        page.goto(item_url, wait_until='domcontentloaded', timeout=15000)
        time.sleep(1)
        
        # Photos
        photos = page.evaluate("""() => {
            const imgs = Array.from(document.querySelectorAll('.item-photo--1 img, .item-photos img'));
            return imgs.map(img => img.src).filter(src => src && src.includes('images.vinted'));
        }""")
        
        # Description
        desc = page.evaluate("() => document.querySelector('[itemprop=\"description\"]')?.innerText || ''")
        
        # API Fallback pour marque/taille si besoin
        import re
        id_match = re.search(r'/items/(\d+)', item_url)
        item_id = id_match.group(1) if id_match else None
        
        brand, size, status = "N/A", "N/A", "N/A"
        if item_id:
            api_data = page.evaluate(f"""async () => {{
                try {{
                    const r = await fetch('/api/v2/items/{item_id}?localize=false');
                    return r.ok ? await r.json() : null;
                }} catch(e) {{ return null; }}
            }}""")
            if api_data and 'item' in api_data:
                it = api_data['item']
                brand = it.get('brand_title', 'N/A')
                size = it.get('size_title', 'N/A')
                status = it.get('status', 'N/A')

        return {
            "description": desc,
            "photos": photos,
            "brand": brand,
            "size": size,
            "status": status
        }
    except:
        return {"description": "", "photos": [], "brand": "N/A", "size": "N/A", "status": "N/A"}

def extract_items_from_page(page):
    try:
        return page.evaluate("""() => {
            const items = [];
            const elements = document.querySelectorAll('div[data-testid*="item"]');
            elements.forEach((el) => {
                const a = el.querySelector('a');
                if (!a) return;
                const url = a.href;
                const idMatch = url.match(/items\\/(\\d+)/);
                if (!idMatch) return;
                
                // Détection Vendeur
                const sellerEl = el.querySelector('h4[class*="Text"], [class*="seller"]');
                const seller = sellerEl ? sellerEl.innerText.trim() : "Inconnu";
                
                const title = a.getAttribute('title') || "Maillot ASSE";
                const priceMatch = el.innerText.match(/\\d+[.,]\\d+\\s*[$€]/);
                const price = priceMatch ? priceMatch[0] : 'N/A';

                items.push({
                    id: parseInt(idMatch[1]),
                    url: url,
                    title: title,
                    price: price,
                    seller: seller,
                    // Signature unique combine Vendeur + Titre + Prix
                    signature: seller + "_" + title + "_" + price
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
        
        f_desc = clean_text(d['description'])
        desc_preview = f_desc[:1000] + "..." if len(f_desc) > 1000 else (f_desc if f_desc else "Pas de description")
        
        import re
        clean_title = item['title'].split(',')[0].split('·')[0].strip()
        clean_title = re.sub(r'\\d+[.,]\\d+\\s*€.*$', '', clean_title).strip()
        if not clean_title: clean_title = "Maillot ASSE"

        payload = {
            "content": f"@everyone | {clean_title}\n💰 {item['price']} | 📏 {d['size']} | 🏷️ {d['brand']} | 👤 {item['seller']}\n📝 {desc_preview}",
            "username": "Vinted ASSE Bot",
            "avatar_url": "https://images.vinted.net/assets/icon-76x76-precomposed-3e6e4c5f0b8c7e5a5c5e5e5e5e5e5e5e.png",
            "embeds": [{
                "title": f"🔔 {clean_title}", "url": item['url'], "color": 0x09B83E,
                "description": f"**{item['price']}** | Taille: **{d['size']}**\nVendeur: **{item['seller']}**\n\n{f_desc[:300]}...",
                "image": {"url": d['photos'][0] if d['photos'] else ""},
                "footer": {"text": f"Vinted Bot • Anti-Repost Active"},
                "timestamp": datetime.utcnow().isoformat() + "Z"
            }]
        }
        requests.post(DISCORD_WEBHOOK_URL, json=payload, timeout=10)
        log(f"✅ Alerte envoyée: {item['title']} (#{item['id']})")
    except Exception as e:
        log(f"❌ Erreur Alert: {e}")

def watchdog_handler(signum, frame):
    log("🚨 WATCHDOG ! Redémarrage..."); os._exit(1)

def run_bot():
    log("🚀 Démarrage SNIPER V11.18 (Auto Anti-Repost)")
    
    # Chargement historique
    last_id = load_last_seen_id()
    sent_signatures = load_json(SIGNATURES_FILE, [])
    # On garde les 500 dernières signatures pour rester léger
    if len(sent_signatures) > 500: sent_signatures = sent_signatures[-500:]

    seen_ids = set()
    initialized_queries = set()
    last_green_check = 0
    last_secondary_check = 0
    
    # Cycle silencieux uniquement si c'est le tout premier lancement (zéro historique)
    is_initial_run = (last_id == 0)
    if is_initial_run:
        log("🆕 Premier lancement détecté. Premier cycle silencieux.")
    else:
        log(f"🔄 Reprise d'activité (Dernier ID : {last_id})")

    while True:
        try:
            gc.collect()
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True, args=['--no-sandbox', '--disable-dev-shm-usage', '--disable-gpu'])
                context = browser.new_context(user_agent="Mozilla/5.0", locale="fr-FR")
                
                # Blocage agressif (NICKEL mode)
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

                signal.signal(signal.SIGALRM, watchdog_handler); signal.alarm(300)

                for q, c in queries:
                    q_key = f"{q}_{c}"
                    try:
                        page = context.new_page()
                        page.goto(get_search_url(q, c), wait_until="domcontentloaded", timeout=25000)
                        items = extract_items_from_page(page)
                        
                        is_new_query = q_key not in initialized_queries
                        for it in items:
                            if it['id'] in seen_ids: continue
                            seen_ids.add(it['id'])
                            
                            if it['id'] > last_id:
                                # VÉRIFICATION ANTI-REPOST (Signature)
                                if it['signature'] in sent_signatures:
                                    log(f"🚫 Doublon (Signature déjà envoyée) : {it['title']} ({it['seller']})")
                                    continue
                                
                                # Filtrage Club
                                t = it['title'].lower()
                                team_kw = ["asse", "saint etienne", "saint-etienne", "st etienne", "st-etienne", "sainté", "sainte", "as st", "as saint", "vert"]
                                wear_kw = ["maillot", "jersey", "maglia", "camiseta", "trikot", "ensemble", "reproduction"]
                                
                                if any(k in t for k in team_kw) and (any(k in t for k in wear_kw) or c == 10):
                                    if not (is_initial_run and is_new_query):
                                        send_discord_alert(context, it)
                                        sent_signatures.append(it['signature'])
                                        if len(sent_signatures) > 500: sent_signatures.pop(0)
                                        save_json(SIGNATURES_FILE, sent_signatures)
                                    
                                    last_id = max(last_id, it['id'])
                                    with open(STATE_FILE, "w") as f: f.write(str(last_id))
                        
                        initialized_queries.add(q_key)
                        page.close()
                    except Exception as e:
                        log(f"⚠️ Erreur {q}: {e}")

                browser.close()
                signal.alarm(0)
                
                # Entretien Cache IDs
                if len(seen_ids) > 2000:
                    ids_sorted = sorted(list(seen_ids), reverse=True)
                    seen_ids = set(ids_sorted[:1500])

                log("⏳ Cycle terminé. Repos 10s...")
                time.sleep(10)

        except Exception as e:
            log(f"🚨 Bug global : {e}"); time.sleep(20)

if __name__ == "__main__":
    run_bot()
