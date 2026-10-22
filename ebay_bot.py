#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
eBay ASSE Jersey Sniper
Surveillance en temps réel des maillots de l'ASSE sur eBay.fr via l'API officielle Browse.
Filtre exclusif : Achat Immédiat (Buy It Now).
Zéro impact sur Vinted, consommation API < 15% du quota gratuit quotidien.
"""

import os
import sys
import time
import json
import base64
import random
import requests
from datetime import datetime, timezone, timedelta

# Chargement du fichier .env local ou serveur
def load_env_file():
    candidates = [
        os.path.join(os.path.dirname(__file__), ".env"),
        "/root/JerseyAlert/.env",
        ".env"
    ]
    for p in candidates:
        if os.path.exists(p):
            try:
                with open(p, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if line and not line.startswith("#") and "=" in line:
                            k, v = line.split("=", 1)
                            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))
                break
            except Exception:
                pass

load_env_file()

# Identifiants eBay Production (lus depuis .env)
EBAY_CLIENT_ID = os.environ.get("EBAY_CLIENT_ID", "")
EBAY_CLIENT_SECRET = os.environ.get("EBAY_CLIENT_SECRET", "")

# Discord Webhook (utilise le même webhook que Vinted)
DISCORD_WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL")

# Fichier de cache des annonces déjà alertées
STATE_DIR = "/root/JerseyAlert" if os.path.exists("/root/JerseyAlert") else os.path.dirname(os.path.abspath(__file__))
SEEN_IDS_FILE = os.path.join(STATE_DIR, "seen_ids_ebay.json")

# Fréquence de scan (120 secondes par défaut = ~720 requêtes/jour sur 5 000 gratuites)
SCAN_INTERVAL = int(os.environ.get("EBAY_SCAN_INTERVAL", "120"))

# Heure de Paris
PARIS_TZ = timezone(timedelta(hours=2))

def get_paris_time():
    return datetime.now(PARIS_TZ)

def log(msg):
    ts = get_paris_time().strftime('%Y-%m-%d %H:%M:%S')
    print(f"[{ts}] {msg}", flush=True)

# Import des filtres ASSE de pointe développés pour Vinted
try:
    from vinted_bot_oracle import (
        is_excluded_product,
        is_asse_jersey_match,
        is_seller_blacklisted,
        is_excluded_size,
        FILTER_ADULT_ONLY
    )
except ImportError:
    log("⚠️ Import direct de vinted_bot_oracle indisponible, utilisation du moteur de secours...")
    def is_asse_jersey_match(t):
        import re
        return bool(re.search(r'\b(asse|saint[- \.]*etienne|st[- \.]*etienne|saint[eé])\b', (t or '').lower()))
    def is_excluded_product(t, d, p):
        return False, "OK"
    def is_seller_blacklisted(s):
        return False
    def is_excluded_size(s, t, d=""):
        return False, "OK"
    FILTER_ADULT_ONLY = True

# Gestion du Token OAuth 2.0 Client Credentials
class EbayTokenManager:
    def __init__(self, client_id, client_secret):
        self.client_id = client_id
        self.client_secret = client_secret
        self.token = None
        self.expires_at = 0

    def get_token(self):
        now = time.time()
        # Si le token est encore valide pour au moins 5 minutes, on le réutilise
        if self.token and (self.expires_at - now) > 300:
            return self.token

        token_url = "https://api.ebay.com/identity/v1/oauth2/token"
        auth_str = f"{self.client_id}:{self.client_secret}"
        auth_b64 = base64.b64encode(auth_str.encode("utf-8")).decode("utf-8")
        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
            "Authorization": f"Basic {auth_b64}"
        }
        data = {
            "grant_type": "client_credentials",
            "scope": "https://api.ebay.com/oauth/api_scope"
        }

        try:
            resp = requests.post(token_url, headers=headers, data=data, timeout=10)
            if resp.status_code == 200:
                res_json = resp.json()
                self.token = res_json.get("access_token")
                expires_in = res_json.get("expires_in", 7200)
                self.expires_at = now + expires_in
                log("🔑 [eBay] Nouveau token OAuth acquis avec succès.")
                return self.token
            else:
                log(f"🚨 [eBay] Échec token OAuth (HTTP {resp.status_code}) : {resp.text}")
                return None
        except Exception as e:
            log(f"🚨 [eBay] Erreur connexion token OAuth : {e}")
            return None

def load_seen_ids():
    if os.path.exists(SEEN_IDS_FILE):
        try:
            with open(SEEN_IDS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                return set(data)
        except Exception:
            pass
    return set()

def save_seen_ids(seen_set):
    try:
        # Garder au plus les 5 000 derniers IDs pour ne pas saturer le fichier
        id_list = list(seen_set)[-5000:]
        with open(SEEN_IDS_FILE, "w", encoding="utf-8") as f:
            json.dump(id_list, f)
    except Exception as e:
        log(f"⚠️ [eBay] Erreur sauvegarde seen_ids: {e}")

def send_discord_alert(item):
    if not DISCORD_WEBHOOK_URL:
        log("⚠️ [eBay] DISCORD_WEBHOOK_URL non configuré !")
        return

    title = item.get("title", "Maillot ASSE")
    item_url = item.get("itemWebUrl", "")
    item_id = item.get("legacyItemId") or item.get("itemId", "").split("|")[1] if "|" in item.get("itemId", "") else item.get("itemId", "")
    
    price_info = item.get("price", {})
    price_val = price_info.get("value", "N/A")
    currency = "€" if price_info.get("currency") == "EUR" else price_info.get("currency", "")
    price_str = f"{price_val} {currency}"

    # Frais de port
    shipping_str = ""
    shipping_opts = item.get("shippingOptions", [])
    if shipping_opts:
        ship_cost = shipping_opts[0].get("shippingCost", {}).get("value")
        if ship_cost:
            try:
                s_float = float(ship_cost)
                if s_float == 0.0:
                    shipping_str = "Gratuite"
                else:
                    shipping_str = f"+ {s_float:.2f} {currency}"
            except Exception:
                shipping_str = f"+ {ship_cost} {currency}"

    condition = item.get("condition", "Occasion")
    seller_info = item.get("seller", {})
    seller_name = seller_info.get("username", "Inconnu")
    feedback_score = seller_info.get("feedbackScore")
    feedback_pct = seller_info.get("feedbackPercentage")

    # Images HD
    photos = []
    # Photo principale (remplace s-l225 par s-l1600 pour la haute définition)
    main_img = item.get("image", {}).get("imageUrl", "")
    if main_img:
        photos.append(main_img.replace("/s-l225.", "/s-l1600.").replace("/s-l500.", "/s-l1600."))

    for add_img in item.get("additionalImages", []):
        u = add_img.get("imageUrl", "")
        if u:
            hd = u.replace("/s-l225.", "/s-l1600.").replace("/s-l500.", "/s-l1600.")
            if hd not in photos:
                photos.append(hd)

    # Construction de la description
    desc_lines = [
        f"💰 Prix : **{price_str}**" + (f" *({shipping_str})*" if shipping_str else "") + " | ⚡ **Achat Immédiat**",
        f"🏷️ État : **{condition}**"
    ]
    if seller_name:
        seller_line = f"👤 Vendeur : **{seller_name}**"
        if feedback_score is not None and feedback_pct:
            seller_line += f" *(★ {feedback_score} • {feedback_pct}% positifs)*"
        desc_lines.append(seller_line)

    desc_lines.append(f"\n🔗 [Voir l'annonce sur eBay.fr]({item_url})")

    # Construction du payload Discord (jusqu'à 4 photos regroupées en galerie)
    embeds = []
    embed1 = {
        "title": f"🛒 [eBay Achat Immédiat] {title}",
        "url": item_url,
        "description": "\n".join(desc_lines),
        "color": 0x0064D2,  # Bleu officiel eBay
        "image": {"url": photos[0]} if photos else {},
        "footer": {"text": f"eBay Sniper • ID: {item_id}"}
    }
    embeds.append(embed1)

    for p in photos[1:4]:
        embeds.append({
            "url": item_url,
            "image": {"url": p}
        })

    payload = {
        "username": "eBay ASSE Sniper",
        "avatar_url": "https://upload.wikimedia.org/wikipedia/commons/thumb/1/1b/EBay_logo.svg/200px-EBay_logo.svg.png",
        "embeds": embeds
    }

    try:
        r = requests.post(DISCORD_WEBHOOK_URL, json=payload, timeout=8)
        if r.status_code in (200, 204):
            log(f"✅ [eBay] Alerte envoyée sur Discord pour #{item_id} : '{title}' ({price_str})")
        else:
            log(f"⚠️ [eBay] Erreur webhook Discord (HTTP {r.status_code}) : {r.text[:200]}")
    except Exception as e:
        log(f"❌ [eBay] Erreur envoi Discord: {e}")

def run_ebay_sniper():
    log("🚀 [eBay] Démarrage du Sniper eBay ASSE (API Browse Officielle)")
    log("⚡ [eBay] Filtre strict : Achat Immédiat uniquement (Buy It Now)")
    log(f"⏱️ [eBay] Fréquence : 1 scan toutes les {SCAN_INTERVAL}s (~{int(86400/SCAN_INTERVAL)} req/jour sur 5 000 gratuites)")

    token_mgr = EbayTokenManager(EBAY_CLIENT_ID, EBAY_CLIENT_SECRET)
    seen_ids = load_seen_ids()
    is_initial_run = (len(seen_ids) == 0)

    search_url = "https://api.ebay.com/buy/browse/v1/item_summary/search"
    query_str = "maillot (asse, saint etienne, st etienne)"

    while True:
        try:
            token = token_mgr.get_token()
            if not token:
                time.sleep(30)
                continue

            headers = {
                "Authorization": f"Bearer {token}",
                "X-EBAY-C-MARKETPLACE-ID": "EBAY_FR"
            }
            params = {
                "q": query_str,
                "sort": "newlyListed",
                "filter": "buyingOptions:{FIXED_PRICE}",
                "limit": 50
            }

            resp = requests.get(search_url, headers=headers, params=params, timeout=12)
            if resp.status_code == 200:
                data = resp.json()
                items = data.get("itemSummaries", [])
                log(f"🔎 [eBay] Scan effectué : {len(items)} annonces récentes")

                new_matches = []
                now_utc = datetime.now(timezone.utc)

                for it in items:
                    raw_id = it.get("legacyItemId") or (it.get("itemId", "").split("|")[1] if "|" in it.get("itemId", "") else it.get("itemId", ""))
                    if not raw_id:
                        continue

                    # Déjà vu
                    if raw_id in seen_ids:
                        continue

                    seen_ids.add(raw_id)

                    title = it.get("title", "")
                    price_val = it.get("price", {}).get("value", "0")
                    opts = it.get("buyingOptions", [])
                    seller_name = it.get("seller", {}).get("username", "")

                    # 1. Vérification formelle Achat Immédiat PUR (exclut les enchères mixtes et les enchères en cours)
                    if "FIXED_PRICE" not in opts or "AUCTION" in opts:
                        continue
                    if it.get("currentBidPrice") or it.get("bidCount", 0) > 0:
                        continue

                    # 2. Vérification fraîcheur : annonce déposée il y a moins de 60 minutes
                    created_str = it.get("itemCreationDate")
                    if created_str:
                        try:
                            created_dt = datetime.fromisoformat(created_str.replace("Z", "+00:00"))
                            age_minutes = (now_utc - created_dt).total_seconds() / 60
                            if age_minutes > 60:
                                # Annonce trop ancienne (> 1 heure), ignorée silencieusement
                                continue
                        except Exception:
                            pass

                    # 3. Vérification correspondance ASSE
                    if not is_asse_jersey_match(title):
                        continue

                    # 4. Filtrage des produits exclus (goodies, porte-clés, autocollants, mugs, etc.)
                    is_excl, reason = is_excluded_product(title, "", f"{price_val} €")
                    if is_excl:
                        log(f"🚫 [eBay] Article exclu ({reason}) : '{title}'")
                        continue

                    # 5. Filtrage vendeur bloqué
                    if seller_name and is_seller_blacklisted(seller_name):
                        log(f"🚫 [eBay] Vendeur bloqué @{seller_name} : '{title}'")
                        continue

                    new_matches.append(it)

                save_seen_ids(seen_ids)

                if is_initial_run:
                    log(f"ℹ️ [eBay] Initialisation terminée : {len(seen_ids)} annonces existantes mémorisées (pas de spam initial).")
                    is_initial_run = False
                else:
                    for it in new_matches:
                        send_discord_alert(it)
                        time.sleep(1)

            elif resp.status_code == 401:
                log("⚠️ [eBay] Token expiré, renouvellement au prochain cycle...")
                token_mgr.token = None
            else:
                log(f"⚠️ [eBay] Erreur réponse API (HTTP {resp.status_code}) : {resp.text[:200]}")

        except Exception as e:
            log(f"🚨 [eBay] Exception cycle de scan : {e}")

        # Pause avec un léger jitter anti-régularité (~115 à 125s)
        jitter = random.uniform(-5, 5)
        time.sleep(max(30, SCAN_INTERVAL + jitter))

if __name__ == "__main__":
    try:
        run_ebay_sniper()
    except KeyboardInterrupt:
        log("⛔ [eBay] Arrêt demandé.")
