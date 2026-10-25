#!/usr/bin/env python3
"""
Vintage Football Area (VFA) Sniper - Alertes Maillots ASSE en temps réel
- Surveillance automatique de la collection ASSE sur Vintage Football Area (Shopify JSON API)
- Extraction instantanée des détails riches (État, Taille, Équipementier, Joueurs, Histoire)
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
import requests

# Charger les variables d'environnement
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# Importer les filtres ASSE officiels du projet
try:
    from vinted_bot_oracle import is_asse_jersey_match, is_excluded_product, is_excluded_size, clean_text
except ImportError:
    def clean_text(txt):
        return (txt or "").strip()

    def is_asse_jersey_match(title):
        if not title: return False
        t = title.lower()
        if re.search(r'\b(saint[eé][- ]?lyon|course\s*(?:a|à)\s*pied|marathon|trail)\b', t):
            return False
        return bool(re.search(r'\b(asse|saint[- \.]*etienne|st[- \.]*etienne|sainté|saint[- \.]*étienne|st[- \.]*étienne)\b', t))

    def is_excluded_product(title, description="", price_str=""):
        return False, ""

    def is_excluded_size(size_str, title_str="", desc_str=""):
        return False, ""

VFA_COLLECTION_URL = "https://www.vintagefootballarea.com/collections/asse/products.json?limit=50&sort_by=created-descending"
DISCORD_WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL")
SEEN_IDS_FILE = "seen_vfa_ids.json"

CHECK_INTERVAL_MIN = 45
CHECK_INTERVAL_MAX = 75

def log(msg):
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{now}] [VFA] {msg}", flush=True)

def load_seen_ids():
    if os.path.exists(SEEN_IDS_FILE):
        try:
            with open(SEEN_IDS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                return set(data)
        except Exception:
            pass
    if os.path.exists("last_seen_vfa_id.txt"):
        try:
            with open("last_seen_vfa_id.txt", "r") as f:
                old_id = f.read().strip()
                if old_id:
                    return {old_id}
        except Exception:
            pass
    return set()

def save_seen_ids(seen_set):
    try:
        id_list = list(seen_set)[-1000:]
        with open(SEEN_IDS_FILE, "w", encoding="utf-8") as f:
            json.dump(id_list, f)
    except Exception as e:
        log(f"⚠️ Erreur sauvegarde seen_ids: {e}")

def parse_body_html(html_str):
    """Extrait proprement les métadonnées de la description HTML Shopify VFA"""
    if not html_str:
        return {}
    
    # Nettoyage balises HTML basiques
    text = re.sub(r'<br\s*/?>', '\n', html_str)
    text = re.sub(r'</p>', '\n', text)
    text = re.sub(r'<[^>]+>', ' ', text)
    text = re.sub(r'&nbsp;', ' ', text)
    text = re.sub(r'[ \t]+', ' ', text)
    
    meta = {}
    for line in text.split('\n'):
        line = line.strip()
        if not line or ':' not in line:
            continue
        parts = line.split(':', 1)
        key = parts[0].strip().lower()
        val = parts[1].strip()
        if 'etat' in key or 'état' in key:
            meta['etat'] = val
        elif 'taille' in key:
            meta['taille'] = val
        elif 'equipementier' in key or 'équipementier' in key:
            meta['marque'] = val
        elif 'joueur' in key:
            meta['joueurs'] = val
        elif 'histoire' in key:
            meta['histoire'] = val
        elif 'le maillot en détail' in key:
            meta['detail'] = val
            
    return meta

def extract_vfa_size(prod, meta=None):
    title = prod.get("title", "")
    # 1. Vérification dans le titre type "2020/21 - Saint-Etienne (S)" ou "(XL)"
    m_size = re.search(r'\(([^)]+)\)$', title)
    if m_size:
        return m_size.group(1).strip()
    
    # 2. Vérification dans les tags Shopify type "Taille S", "Taille M"
    tags = prod.get("tags", [])
    if isinstance(tags, str):
        tags = [t.strip() for t in tags.split(",")]
    for tag in tags:
        m_tag = re.search(r'taille\s+([a-z0-9/]+)', tag, re.I)
        if m_tag:
            return m_tag.group(1).strip()
            
    # 3. Vérification dans les options / variantes Shopify
    for opt in prod.get("options", []):
        if opt.get("name", "").lower() in ("taille", "size"):
            vals = opt.get("values", [])
            if vals and vals[0] != "Default Title":
                return vals[0].strip()
                
    # 4. Vérification dans le body HTML parsé
    if meta and meta.get("taille"):
        return meta["taille"].strip()
        
    return ""

def fetch_vfa_single_product(handle):
    if not handle:
        return None
    url = f"https://www.vintagefootballarea.com/products/{handle}.json"
    headers = {
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
        'Accept': 'application/json, text/plain, */*'
    }
    try:
        resp = requests.get(url, headers=headers, timeout=8)
        if resp.status_code == 200:
            return resp.json().get("product")
    except Exception as e:
        log(f"⚠️ Erreur fetch single product '{handle}': {e}")
    return None

def send_discord_alert(product):
    if not DISCORD_WEBHOOK_URL:
        log("⚠️ DISCORD_WEBHOOK_URL non configuré !")
        return

    product_id = str(product.get("id", ""))
    title = clean_text(product.get("title", "Maillot ASSE"))
    handle = product.get("handle", "")
    item_url = f"https://www.vintagefootballarea.com/products/{handle}" if handle else "https://www.vintagefootballarea.com/collections/asse"
    
    # Prix & Disponibilité & Promotions
    variants = product.get("variants", [])
    avail_vars = [v for v in variants if v.get("available")]
    var = avail_vars[0] if avail_vars else (variants[0] if variants else {})
    raw_price = var.get("price", "N/A")
    compare_at = var.get("compare_at_price")

    try:
        p_float = float(raw_price)
        if compare_at and float(compare_at) > p_float:
            price_display = f"~~{float(compare_at):.2f} €~~ **{p_float:.2f} €** (Promo)"
        else:
            price_display = f"**{p_float:.2f} €**"
    except (ValueError, TypeError):
        price_display = f"**{raw_price} €**"

    # Images
    images = product.get("images", [])
    photos = [img.get("src") for img in images if isinstance(img, dict) and img.get("src")]

    # Métadonnées extraites de body_html
    body_html = product.get("body_html", "")
    meta = parse_body_html(body_html)
    
    # Taille propre
    size_str = extract_vfa_size(product, meta) or "Voir fiche"

    condition_str = meta.get("etat") or "Occasion vintage"
    brand_str = meta.get("marque") or ""
    players_str = meta.get("joueurs") or ""
    history_str = meta.get("histoire") or meta.get("detail") or ""

    # Construction de la description
    desc_lines = [
        f"💰 Prix : {price_display} | 📏 Taille : **{size_str}**",
        f"🏷️ État : **{condition_str}**" + (f" | 👕 Marque : **{brand_str}**" if brand_str else "")
    ]
    if players_str:
        desc_lines.append(f"👥 Joueurs : **{players_str}**")
    if history_str:
        preview = history_str[:250] + ("..." if len(history_str) > 250 else "")
        desc_lines.append(f"\n📖 *{preview}*")

    desc_lines.append(f"\n🔗 [Voir l'annonce sur Vintage Football Area]({item_url})")

    embed1 = {
        "title": f"🟢 [VFA] {title}",
        "url": item_url,
        "description": "\n".join(desc_lines),
        "color": 0x1B4D3E,  # Vert Forêt Vintage
        "footer": {"text": f"VFA Sniper • ID: {product_id}"},
        "timestamp": datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S.%f')[:-3] + 'Z'
    }
    if photos:
        embed1["image"] = {"url": photos[0]}

    embeds = [embed1]
    for p in photos[1:4]:
        embeds.append({"url": item_url, "image": {"url": p}})

    payload = {
        "username": "Vintage Football Area Sniper",
        "avatar_url": "https://www.vintagefootballarea.com/cdn/shop/files/favicon-32x32_32x32.png",
        "embeds": embeds
    }

    try:
        r = requests.post(DISCORD_WEBHOOK_URL, json=payload, timeout=8)
        if r.status_code in (200, 204):
            log(f"✅ Alerte envoyée sur Discord pour #{product_id} : '{title}' ({price_display})")
        else:
            log(f"⚠️ Erreur Discord (HTTP {r.status_code}) : {r.text[:200]}")
    except Exception as e:
        log(f"❌ Erreur envoi webhook Discord: {e}")

def fetch_vfa_products():
    headers = {
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
        'Accept': 'application/json, text/plain, */*',
        'Accept-Language': 'fr-FR,fr;q=0.9,en-US;q=0.8,en;q=0.7'
    }
    try:
        resp = requests.get(VFA_COLLECTION_URL, headers=headers, timeout=12)
        if resp.status_code == 200:
            data = resp.json()
            return data.get("products", [])
        else:
            log(f"⚠️ Réponse HTTP {resp.status_code} de Vintage Football Area")
            return []
    except Exception as e:
        log(f"⚠️ Erreur requête VFA: {e}")
        return []

def run_bot():
    log("🚀 Démarrage du Sniper Vintage Football Area ASSE (Shopify API)")
    seen_ids = load_seen_ids()
    is_initial_run = (len(seen_ids) == 0)

    cycle_count = 0
    while True:
        cycle_count += 1
        try:
            products = fetch_vfa_products()
            if not products:
                time.sleep(30)
                continue

            if cycle_count % 10 == 1:
                log(f"🔎 Scan #{cycle_count} : {len(products)} produits analysés ({len(seen_ids)} en mémoire)")

            new_valid_products = []
            for prod in products:
                prod_id = str(prod.get("id", ""))
                if not prod_id:
                    continue

                if prod_id in seen_ids:
                    continue

                seen_ids.add(prod_id)

                title = prod.get("title", "")
                body = prod.get("body_html", "") or ""
                variants = prod.get("variants", [])

                # 1. Vérification disponibilité (Stock)
                available = any(v.get("available", False) for v in variants)
                if not available and variants:
                    log(f"🚫 Produit exclu (Rupture de stock / Épuisé) : '{title}'")
                    continue

                # 2. Vérification ASSE
                if not is_asse_jersey_match(title):
                    continue

                # 3. Vérification stricte des tailles (exclusion XS/S)
                meta = parse_body_html(body)
                size_str = extract_vfa_size(prod, meta)
                if size_str:
                    is_excl_size, reason_size = is_excluded_size(size_str, title, body)
                    if is_excl_size:
                        log(f"🚫 Produit exclu ({reason_size}) : '{title}' (Taille: {size_str})")
                        continue
                else:
                    is_excl_size, reason_size = is_excluded_size("", title, body)
                    if is_excl_size:
                        log(f"🚫 Produit exclu ({reason_size}) : '{title}'")
                        continue

                # 4. Filtrage strict produits (Règles 1 à 25)
                first_var = variants[0] if variants else {}
                try:
                    price = float(first_var.get("price", 0.0))
                except (ValueError, TypeError):
                    price = 0.0
                price_str = f"{price:.2f} €"

                is_excl, reason = is_excluded_product(title, body, price_str)
                if is_excl:
                    log(f"🚫 Produit exclu ({reason}) : '{title}' ({price_str})")
                    continue

                new_valid_products.append(prod)

            save_seen_ids(seen_ids)

            if is_initial_run:
                log(f"📋 Initialisation terminée : {len(seen_ids)} produits VFA existants mémorisés.")
                is_initial_run = False
            else:
                for prod in new_valid_products:
                    # Double-check frais via l'API fiche produit individuelle si disponible
                    handle = prod.get("handle")
                    if handle:
                        fresh = fetch_vfa_single_product(handle)
                        if fresh:
                            prod = fresh
                    send_discord_alert(prod)

        except Exception as e:
            log(f"🚨 Erreur cycle VFA: {e}")

        sleep_sec = random.uniform(CHECK_INTERVAL_MIN, CHECK_INTERVAL_MAX)
        time.sleep(sleep_sec)

if __name__ == "__main__":
    run_bot()
