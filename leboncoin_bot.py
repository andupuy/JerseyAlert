#!/usr/bin/env python3
"""
LeBonCoin Bot - Alertes Maillots ASSE en temps réel
- Surveillance automatique de LeBonCoin (sort=time)
- Extraction multi-photos haute résolution (rule=ad-large)
- Filtrage strict ASSE (0 faux positif)
- Notifications enrichies Discord Webhook
"""

import os
import sys
import time
import random
import re
import requests
import signal
from datetime import datetime
from playwright.sync_api import sync_playwright

# Configuration
SEARCH_URL = "https://www.leboncoin.fr/recherche?text=maillot%20asse&sort=time"
DISCORD_WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL")
STATE_FILE = "last_seen_lbc_id.txt"
CHECK_INTERVAL_MIN = 30
CHECK_INTERVAL_MAX = 45

def log(message):
    """Log avec timestamp"""
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    print(f"[{timestamp}] [LeBonCoin] {message}", flush=True)

def load_last_seen_id():
    """Charge le dernier ID vu depuis le fichier"""
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r") as f:
                return int(f.read().strip())
        except Exception:
            pass
    return 0

def save_last_seen_id(item_id):
    """Sauvegarde le dernier ID vu"""
    try:
        with open(STATE_FILE, "w") as f:
            f.write(str(item_id))
    except Exception as e:
        log(f"⚠️ Erreur sauvegarde ID: {e}")

def is_asse_match(title):
    """Filtrage strict ASSE avec limites de mots (évite faux positifs tout en capturant tous les produits ASSE)"""
    if not title:
        return False
    title_low = title.lower()
    team_pattern = r'\b(asse|saint[- \.]*etienne|st[- \.]*etienne|sainté|saint[- \.]*étienne|st[- \.]*étienne)\b'
    return bool(re.search(team_pattern, title_low))

def scrape_ad_details(page, ad_url):
    """Ouvre la page de l'annonce LeBonCoin pour récupérer toutes les photos HD et la description"""
    try:
        log(f"🔎 Scraping détails LBC: {ad_url}")
        page.goto(ad_url, wait_until='domcontentloaded', timeout=15000)
        page.wait_for_timeout(2000)
        
        details = page.evaluate("""() => {
            const imgs = Array.from(document.querySelectorAll('img'))
                                .map(i => i.src || i.getAttribute('data-src') || '')
                                .filter(src => src && src.includes('img.leboncoin.fr/api/v1/lbcpb/images'));
            
            // URLs grand format HD
            const cleanImgs = imgs.map(url => url.replace(/rule=[^&]+/, 'rule=ad-large'));
            
            const descEl = document.querySelector('[data-qa-id="adview_description_container"]') || 
                           document.querySelector('div[class*="description"]') || 
                           document.body;
                           
            return {
                photos: Array.from(new Set(cleanImgs)),
                description: descEl ? descEl.innerText.replace(/\\n+/g, '\\n').trim() : ''
            };
        }""")
        return details
    except Exception as e:
        log(f"⚠️ Erreur scraping détails LBC: {e}")
        return {"photos": [], "description": ""}

def send_discord_alert(context, item):
    """Envoie une alerte Discord enrichie pour LeBonCoin"""
    if not DISCORD_WEBHOOK_URL:
        log("⚠️ Aucun DISCORD_WEBHOOK_URL configuré. Notification sautée.")
        return

    # Récupération des détails riches (Toutes les photos HD + Description)
    details = {"photos": [], "description": ""}
    try:
        detail_page = context.new_page()
        details = scrape_ad_details(detail_page, item['url'])
        detail_page.close()
    except Exception as e:
        log(f"⚠️ Erreur création page détails LBC: {e}")

    try:
        title = item.get('title', 'Nouvelle annonce LeBonCoin')
        price = item.get('price', 'N/A')
        location = item.get('location', 'France')
        date_str = item.get('date', '')
        
        photos = details['photos'] if details['photos'] else ([item['photo']] if item.get('photo') else [])
        desc = details['description']
        
        if len(desc) > 500:
            desc = desc[:500] + "..."

        description_text = f"**{price}** | Localisation: **{location}**\n\n{desc}" if desc else f"**{price}** | Localisation: **{location}**"

        embed1 = {
            "title": f"🟠 LeBonCoin : {title}",
            "url": item.get('url'),
            "description": description_text,
            "color": 0xFF6E14,  # Orange LeBonCoin
            "footer": {"text": f"LeBonCoin Bot • ID: {item.get('id')} • {date_str}"},
            "timestamp": datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%S.%f')[:-3] + 'Z'
        }
        
        if photos:
            embed1["image"] = {"url": photos[0]}

        embeds = [embed1]
        for photo_url in photos[1:4]:
            embeds.append({"url": item.get('url'), "image": {"url": photo_url}})

        desc_preview = desc[:500] if desc else "Pas de description"
        notif_text = f"@everyone | 🟠 **LeBonCoin** : {title}\n💰 {price} | 📍 {location}\n📝 {desc_preview}"

        payload = {
            "content": notif_text,
            "username": "LeBonCoin ASSE Bot",
            "avatar_url": "https://www.leboncoin.fr/favicon.ico",
            "embeds": embeds
        }
        requests.post(DISCORD_WEBHOOK_URL, json=payload, timeout=10)
        log(f"✅ Alerte Discord envoyée pour LeBonCoin #{item.get('id')}")

    except Exception as e:
        log(f"❌ Erreur envoi Discord LBC: {e}")

def watchdog_handler(signum, frame):
    """Watchdog freeze detection"""
    log("🚨 WATCHDOG: Bot LeBonCoin figé ! Redémarrage...")
    os._exit(1)

def run_bot():
    """Boucle principale du bot LeBonCoin"""
    log("🚀 Démarrage du Bot LeBonCoin ASSE")
    
    seen_ids = set()
    is_initial_cycle = True
    last_seen_id = load_last_seen_id()

    try:
        while True:
            # Mode veille la nuit (1h à 7h)
            os.environ['TZ'] = 'Europe/Paris'
            if hasattr(time, 'tzset'):
                time.tzset()
            current_hour = time.localtime().tm_hour

            if current_hour >= 1 and current_hour < 7:
                log(f"🌙 Mode Veille Silencieuse activé ({current_hour}h).")
                time.sleep(600)
                continue

            try:
                signal.signal(signal.SIGALRM, watchdog_handler)
                signal.alarm(180)

                with sync_playwright() as p:
                    browser = p.chromium.launch(
                        headless=True,
                        args=['--no-sandbox', '--disable-setuid-sandbox', '--disable-dev-shm-usage', '--disable-gpu']
                    )
                    context = browser.new_context(
                        user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                        viewport={'width': 1280, 'height': 720},
                        locale='fr-FR',
                        timezone_id='Europe/Paris'
                    )

                    page = context.new_page()
                    page.set_default_timeout(20000)
                    
                    log(f"🔎 Consultation LeBonCoin : {SEARCH_URL}")
                    page.goto(SEARCH_URL, wait_until='domcontentloaded', timeout=20000)
                    try:
                        page.wait_for_selector('a[href*="/ad/"]', timeout=10000)
                    except Exception:
                        pass
                    
                    raw_ads = page.evaluate("""() => {
                        const anchors = Array.from(document.querySelectorAll('a[href*="/ad/"]'));
                        return anchors.map(a => {
                            const idMatch = a.href.match(/\\/(\\d+)(\\?|$)/);
                            const parent = a.closest('div') || a.parentElement;
                            const img = a.querySelector('img') || parent.querySelector('img');
                            const textLines = a.innerText.split('\\n').map(t => t.trim()).filter(t => t.length > 0);
                            
                            // Formattage des infos
                            let title = textLines[0] || 'Annonce LeBonCoin';
                            let price = 'N/A';
                            let location = 'France';
                            let date = '';
                            
                            textLines.forEach(line => {
                                if (line.includes('€')) price = line;
                                else if (/\\d{5}/.test(line)) location = line;
                                else if (line.includes('/') || line.includes(':')) date = line;
                            });
                            
                            return {
                                id: idMatch ? parseInt(idMatch[1]) : null,
                                title: title,
                                price: price,
                                location: location,
                                date: date,
                                url: a.href,
                                photo: img ? (img.src || img.getAttribute('data-src') || '') : ''
                            };
                        }).filter(x => x.id && x.title.length > 3);
                    }""")
                    
                    page.close()

                    if raw_ads:
                        new_found = []
                        for ad in raw_ads:
                            if ad['id'] not in seen_ids and ad['id'] > (last_seen_id - 100000):
                                new_found.append(ad)
                                seen_ids.add(ad['id'])
                        
                        if is_initial_cycle:
                            if new_found:
                                last_seen_id = max(last_seen_id, max(x['id'] for x in new_found))
                                log(f"✅ Initialisation terminée. {len(seen_ids)} annonces chargées. Dernier ID: {last_seen_id}")
                        elif new_found:
                            log(f"🆕 {len(new_found)} nouvelles annonces détectées sur LeBonCoin !")
                            new_found.sort(key=lambda x: x['id'])
                            for ad in new_found:
                                if is_asse_match(ad['title']):
                                    log(f"🎯 MATCH LEBONCOIN : '{ad['title']}' ({ad['price']})")
                                    send_discord_alert(context, ad)
                            
                            last_seen_id = max(last_seen_id, max(x['id'] for x in new_found))
                            save_last_seen_id(last_seen_id)
                    
                    browser.close()

                signal.alarm(0)
            except Exception as e:
                log(f"🚨 Bug moteur LeBonCoin : {e}")
                signal.alarm(0)

            is_initial_cycle = False
            if len(seen_ids) > 2000:
                seen_ids_list = sorted(list(seen_ids), reverse=True)
                seen_ids = set(seen_ids_list[:1500])

            sleep_time = random.uniform(CHECK_INTERVAL_MIN, CHECK_INTERVAL_MAX)
            log(f"⏳ Repos {int(sleep_time)}s avant le prochain scan...")
            time.sleep(sleep_time)

    except KeyboardInterrupt:
        log("⛔ Arrêt du bot LeBonCoin")

if __name__ == "__main__":
    run_bot()
