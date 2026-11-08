#!/usr/bin/env python3
"""
LeBonCoin Sniper - Alertes Maillots ASSE en temps réel
- Surveillance automatique de LeBonCoin (sort=time) via SOCKS5 proxy résidentiel (Nvidia Shield)
- Bypasse DataDome sans frais via curl_cffi (impersonate='chrome124')
- Filtrage strict ASSE (Règles 1 à 22 synchronisées avec Vinted)
- Notifications enrichies Discord Webhook optimisées pour Garmin Watch
"""

import os
import sys
import time
import random
import re
import json
from datetime import datetime, timezone
try:
    from zoneinfo import ZoneInfo
except ImportError:
    ZoneInfo = None
from curl_cffi import requests
from dotenv import load_dotenv

# Charger les variables d'environnement
load_dotenv()

# Importer les filtres ASSE officiels du projet
try:
    from vinted_bot_oracle import is_asse_jersey_match, is_excluded_product, clean_text
except ImportError:
    # Fallback minimal si import direct impossible
    def clean_text(txt):
        return (txt or "").strip()

    def is_asse_jersey_match(title):
        if not title: return False
        t = title.lower()
        if re.search(r'\b(saint[eé][- ]?lyon|course\s*(?:a|à)\s*pied|marathon|trail)\b', t):
            return False
        return bool(re.search(r'\b(asse|saint[- \.]*etienne|st[- \.]*etienne|sainté|saint[- \.]*étienne|st[- \.]*étienne)\b', t))

    def is_excluded_product(title, price=0.0, description=""):
        return False, ""

SEARCH_URL = "https://www.leboncoin.fr/recherche?text=maillot%20asse&sort=time"
DISCORD_WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL")
SEEN_IDS_FILE = "seen_lbc_ids.json"
PROXY_URL = os.environ.get("LBC_PROXY_URL", "socks5://127.0.0.1:1055")
ERRORS_LOG_FILE = os.environ.get(
    "ERRORS_LOG_FILE",
    "/root/vinted_errors.log" if os.path.exists("/root") else "vinted_errors.log"
)

CHECK_INTERVAL_MIN = int(os.environ.get("LBC_INTERVAL_MIN", 20))
CHECK_INTERVAL_MAX = int(os.environ.get("LBC_INTERVAL_MAX", 35))

def get_paris_time():
    """Retourne l'heure courante exacte de Paris (été/hiver garanti)"""
    if ZoneInfo:
        try:
            return datetime.now(ZoneInfo("Europe/Paris"))
        except Exception:
            pass
    import time
    os.environ['TZ'] = 'Europe/Paris'
    if hasattr(time, 'tzset'):
        time.tzset()
    return datetime.now()

def log(msg, to_error_log=None):
    """Log horodaté (heure de Paris) avec enregistrement automatique dans ERRORS_LOG_FILE pour le dashboard"""
    now = get_paris_time().strftime("%Y-%m-%d %H:%M:%S")
    formatted = f"[{now}] [LeBonCoin] {msg}"
    print(formatted, flush=True)

    if to_error_log is False:
        return

    should_record = to_error_log is True or (
        msg.lstrip().startswith(("⚠️", "🚨", "❌", "🛡️"))
    )
    if should_record:
        try:
            with open(ERRORS_LOG_FILE, "a", encoding="utf-8") as f:
                f.write(formatted + "\n")
        except Exception:
            pass

def load_seen_ids():
    if os.path.exists(SEEN_IDS_FILE):
        try:
            with open(SEEN_IDS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                return set(data)
        except Exception:
            pass
    # Migration depuis ancien fichier texte si existant
    if os.path.exists("last_seen_lbc_id.txt"):
        try:
            with open("last_seen_lbc_id.txt", "r") as f:
                old_id = f.read().strip()
                if old_id:
                    return {old_id}
        except Exception:
            pass
    return set()

def save_seen_ids(seen_set):
    try:
        # Conserver les 3 000 derniers IDs pour ne pas saturer le disque
        id_list = list(seen_set)[-3000:]
        with open(SEEN_IDS_FILE, "w", encoding="utf-8") as f:
            json.dump(id_list, f)
    except Exception as e:
        log(f"⚠️ Erreur sauvegarde seen_ids: {e}")

def get_attribute_value(attributes, key_name):
    if not attributes:
        return ""
    for attr in attributes:
        if attr.get("key") == key_name:
            return attr.get("value_label") or attr.get("value") or ""
    return ""

def send_discord_alert(ad):
    if not DISCORD_WEBHOOK_URL:
        log("⚠️ DISCORD_WEBHOOK_URL non configuré !")
        return

    ad_id = str(ad.get("list_id", ""))
    title = clean_text(ad.get("subject", "Maillot ASSE"))
    url = ad.get("url", f"https://www.leboncoin.fr/ad/sport_plein_air/{ad_id}")
    
    # Prix
    prices = ad.get("price", [0])
    price_val = prices[0] if prices else 0
    price_str = f"{price_val} €"

    # Attributs
    attrs = ad.get("attributes", [])
    size = get_attribute_value(attrs, "clothing_st") or "Non spécifiée"
    brand = get_attribute_value(attrs, "clothing_brand") or ""
    condition = get_attribute_value(attrs, "condition") or "Occasion"

    # Localisation
    loc = ad.get("location", {})
    city = loc.get("city") or loc.get("city_label") or ""
    zipcode = loc.get("zipcode") or ""
    location_str = f"{city} ({zipcode})" if city and zipcode else (city or zipcode or "France")

    # Vendeur
    owner = ad.get("owner", {})
    seller_name = owner.get("name") or "Particulier"

    # Date
    pub_date = ad.get("first_publication_date", "")

    # Photos HD (large)
    images_info = ad.get("images", {})
    photos = images_info.get("urls_large", []) or images_info.get("urls", [])

    # Description pour notification Garmin et Discord Embed
    desc_lines = [
        f"💰 Prix : **{price_str}** | 📍 Localisation : **{location_str}**",
        f"📏 Taille : **{size}**" + (f" | 🏷️ Marque : **{brand}**" if brand else "") + f" | État : **{condition}**",
        f"👤 Vendeur : **{seller_name}**",
        f"\n🔗 [Voir l'annonce sur LeBonCoin]({url})"
    ]

    embed1 = {
        "title": f"🟠 [LeBonCoin] {title}",
        "url": url,
        "description": "\n".join(desc_lines),
        "color": 0xFF6E14,  # Orange officiel LeBonCoin
        "footer": {"text": f"LeBonCoin Sniper • ID: {ad_id}"},
        "timestamp": datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S.%f')[:-3] + 'Z'
    }
    if photos:
        embed1["image"] = {"url": photos[0]}

    embeds = [embed1]
    # Jusqu'à 4 photos en galerie
    for p in photos[1:4]:
        embeds.append({"url": url, "image": {"url": p}})

    payload = {
        "username": "LeBonCoin ASSE Sniper",
        "avatar_url": "https://www.leboncoin.fr/favicon.ico",
        "embeds": embeds
    }

    try:
        r = requests.post(DISCORD_WEBHOOK_URL, json=payload, timeout=8)
        if r.status_code in (200, 204):
            log(f"✅ Alerte envoyée sur Discord pour #{ad_id} : '{title}' ({price_str})")
        else:
            log(f"⚠️ Erreur Discord (HTTP {r.status_code}) : {r.text[:200]}")
    except Exception as e:
        log(f"❌ Erreur envoi webhook Discord: {e}")

def send_discord_system_alert(title, description, color=0xFFA500):
    """
    Route les alertes techniques/système vers le journal d'erreurs du dashboard web (ERRORS_LOG_FILE)
    sans envoyer de spam sur le salon Discord, réservé exclusivement aux maillots ASSE trouvés.
    """
    first_line = description.splitlines()[0].strip() if description else ""
    summary = f"{title} : {first_line}" if first_line else f"{title}"
    log(summary, to_error_log=True)

def fetch_leboncoin_ads(session):
    headers = {
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
        'Accept-Language': 'fr-FR,fr;q=0.9,en-US;q=0.8,en;q=0.7',
        'sec-ch-ua': '"Chromium";v="124", "Google Chrome";v="124", "Not-A.Brand";v="99"',
        'sec-ch-ua-mobile': '?0',
        'sec-ch-ua-platform': '"macOS"',
        'sec-fetch-dest': 'document',
        'sec-fetch-mode': 'navigate',
        'sec-fetch-site': 'none',
        'sec-fetch-user': '?1',
        'upgrade-insecure-requests': '1'
    }

    proxies = {
        'http': PROXY_URL,
        'https': PROXY_URL
    } if PROXY_URL else None

    try:
        resp = session.get(SEARCH_URL, headers=headers, proxies=proxies, impersonate='chrome124', timeout=15)
        if resp.status_code != 200:
            if resp.status_code == 403:
                # Ne pas saturer les logs d'erreurs à chaque requête isolée ; le parachute consecutive_403 prend le relais
                log(f"⚠️ Réponse HTTP 403 reçue de LeBonCoin (Datadome actif)", to_error_log=False)
            else:
                log(f"⚠️ Réponse HTTP {resp.status_code} reçue de LeBonCoin (Longueur: {len(resp.text)})", to_error_log=True)
            session.cookies.clear()
            return [], resp.status_code
    except Exception as e:
        log(f"⚠️ Erreur requête LeBonCoin: {e}", to_error_log=False)
        session.cookies.clear()
        return [], 0

    # Extraction des données JSON Next.js
    m = re.search(r'<script id=[\"\']__NEXT_DATA__[\"\'][^>]*>(.*?)</script>', resp.text)
    if not m:
        log("⚠️ Impossible de trouver le bloc __NEXT_DATA__ dans la page LeBonCoin")
        return [], 200

    try:
        data = json.loads(m.group(1))
        ads = data.get("props", {}).get("pageProps", {}).get("searchData", {}).get("ads", [])
        return ads, 200
    except Exception as e:
        log(f"⚠️ Erreur parsing JSON Next.js: {e}")
        return [], 200

def run_bot():
    log(f"🚀 Démarrage du Sniper LeBonCoin ASSE (curl_cffi + SOCKS5 Shield - Cadence {CHECK_INTERVAL_MIN}-{CHECK_INTERVAL_MAX}s)")
    seen_ids = load_seen_ids()
    is_initial_run = (len(seen_ids) == 0)

    session = requests.Session()

    cycle_count = 0
    consecutive_403 = 0
    consecutive_conn_err = 0
    conn_alert_sent = False

    while True:
        cycle_count += 1
        try:
            ads, status = fetch_leboncoin_ads(session)

            # Surveillance et alerte coupure proxy SOCKS5 / Shield
            if status == 0:
                consecutive_conn_err += 1
                if consecutive_conn_err >= 3 and not conn_alert_sent:
                    log(f"🚨 Alerte Proxy Résidentiel Déconnecté : les requêtes vers LeBonCoin échouent via SOCKS5 (127.0.0.1:1055) - Vérifier Shield / Tailscale ({consecutive_conn_err}x échecs)", to_error_log=True)
                    conn_alert_sent = True
                time.sleep(15)
                continue
            else:
                if conn_alert_sent and status == 200:
                    log("✅ Proxy LeBonCoin reconnecté et opérationnel : reprise des scans.", to_error_log=False)
                    conn_alert_sent = False
                consecutive_conn_err = 0

            # Parachute de sécurité Datadome
            if status == 403:
                consecutive_403 += 1
                if consecutive_403 >= 2:
                    log(f"🛡️ [Datadome] Détection persistante ({consecutive_403}x HTTP 403) ! Mise en pause automatique de 10 minutes pour protéger l'IP.", to_error_log=True)
                    time.sleep(600)
                    consecutive_403 = 0
                    session = requests.Session()
                    log("🔄 Fin de la pause de sécurité (10 min), reprise des scans LeBonCoin.", to_error_log=False)
                    continue
                else:
                    time.sleep(20)
                    continue
            else:
                consecutive_403 = 0

            if not ads:
                time.sleep(random.uniform(CHECK_INTERVAL_MIN, CHECK_INTERVAL_MAX))
                continue

            if cycle_count % 10 == 1:
                log(f"🔎 Scan #{cycle_count} : {len(ads)} annonces analysées ({len(seen_ids)} en mémoire)")

            new_valid_ads = []
            for ad in ads:
                ad_id = str(ad.get("list_id", ""))
                if not ad_id:
                    continue

                if ad_id in seen_ids:
                    continue

                seen_ids.add(ad_id)

                title = ad.get("subject", "")
                prices = ad.get("price", [0])
                price = float(prices[0]) if prices else 0.0
                price_str = f"{price} €"
                body = ad.get("body", "") or ""

                # 1. Vérification de correspondance maillot ASSE
                if not is_asse_jersey_match(title):
                    continue

                # 2. Filtrage strict anti faux positifs (Règles 1 à 25)
                is_excl, reason = is_excluded_product(title, body, price_str)
                if is_excl:
                    log(f"🚫 Annonce exclue ({reason}) : '{title}' ({price}€)")
                    continue

                new_valid_ads.append(ad)

            save_seen_ids(seen_ids)

            if is_initial_run:
                log(f"📋 Initialisation terminée : {len(seen_ids)} annonces existantes mémorisées.")
                is_initial_run = False
            else:
                for ad in new_valid_ads:
                    send_discord_alert(ad)

            if cycle_count % 30 == 0:
                log(f"💓 Heartbeat: {len(seen_ids)} annonces en mémoire, veille active.")

        except Exception as e:
            log(f"🚨 Erreur durant le cycle: {e}")

        # Pause aléatoire entre 20 et 35 secondes pour discrétion et protection IP
        sleep_sec = random.uniform(CHECK_INTERVAL_MIN, CHECK_INTERVAL_MAX)
        time.sleep(sleep_sec)

if __name__ == "__main__":
    run_bot()
