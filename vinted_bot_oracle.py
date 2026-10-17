#!/usr/bin/env python3
"""
Vinted Bot optimisé pour Oracle Cloud
- Utilise Playwright pour éviter la détection
- Délais aléatoires pour paraître humain
- Gestion robuste des erreurs
- Notifications Discord
"""

import os
import sys
import re
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass
import time
import json
import random
import requests
import signal
import threading
from urllib.parse import quote_plus
from datetime import datetime, timezone
try:
    from zoneinfo import ZoneInfo
except ImportError:
    ZoneInfo = None
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout

# Configuration
# Configuration des recherches
PRIORITY_QUERIES = ["Maillot Asse", "Maillot Saint-Etienne", "Maillot St Etienne"]
SECONDARY_QUERIES = ["Jersey Asse", "Jersey Saint-Etienne", "Maglia Asse", "Camiseta Asse", "Ensemble Asse", "Trikot Asse"]
# Liste combinée pour l'initialisation
SEARCH_QUERIES = PRIORITY_QUERIES + SECONDARY_QUERIES

DISCORD_WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL")
STATE_FILE = "last_seen_id.txt"
SEEN_IDS_FILE = "seen_ids_cache.json"
ALERTED_IDS_FILE = "alerted_ids_cache.json"
FILET_SEEN_IDS_FILE = "filet_seen_ids_cache.json"
ERRORS_LOG_FILE = os.environ.get("ERRORS_LOG_FILE", "/root/vinted_errors.log" if os.path.exists("/root/JerseyAlert") else "vinted_errors.log")
BLACKLIST_FILE = os.environ.get("BLACKLIST_FILE", "/root/JerseyAlert/blacklisted_sellers.json" if os.path.exists("/root/JerseyAlert") else "blacklisted_sellers.json")
FILTER_ADULT_ONLY = os.environ.get("FILTER_ADULT_ONLY", "true").lower() == "true"
CHECK_INTERVAL_MIN = 10
CHECK_INTERVAL_MAX = 20

# Flags d'optimisation Chromium (Stabilité garantie, zéro crash, basse consommation)
CHROMIUM_ARGS = [
    '--no-sandbox',
    '--disable-setuid-sandbox',
    '--disable-dev-shm-usage',
    '--disable-gpu',
    '--disable-software-rasterizer',
    '--disable-background-networking',
    '--disable-background-timer-throttling',
    '--disable-breakpad',
    '--disable-component-update',
    '--disable-extensions',
    '--disable-default-apps',
    '--disable-blink-features=AutomationControlled',
    '--mute-audio'
]

def normalize_seller_name(username):
    """Nettoie et normalise le pseudo vendeur (retire @, espaces, et extrait le pseudo si URL fournie)"""
    if not username:
        return ""
    cleaned = str(username).strip().lower().replace("@", "")
    if "vinted." in cleaned and "/member/" in cleaned:
        part = cleaned.split("/member/")[1].split("?")[0].split("/")[0]
        if "-" in part:
            return part.split("-", 1)[1]
        return part
    return cleaned

def load_blacklisted_sellers():
    """Charge la liste noire des vendeurs Vinted"""
    sellers = set()
    env_blocked = os.environ.get("BLOCKED_SELLERS", "")
    if env_blocked:
        for s in env_blocked.split(","):
            norm = normalize_seller_name(s)
            if norm:
                sellers.add(norm)
                
    if os.path.exists(BLACKLIST_FILE):
        try:
            with open(BLACKLIST_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                for s in data:
                    norm = normalize_seller_name(s)
                    if norm:
                        sellers.add(norm)
        except Exception:
            pass
    return sellers

def save_blacklisted_sellers(sellers_set):
    """Sauvegarde la liste noire des vendeurs Vinted"""
    try:
        norm_list = sorted(list({normalize_seller_name(s) for s in sellers_set if normalize_seller_name(s)}))
        with open(BLACKLIST_FILE, "w", encoding="utf-8") as f:
            json.dump(norm_list, f, indent=2, ensure_ascii=False)
    except Exception as e:
        log(f"⚠️ Erreur sauvegarde blacklist: {e}")

def is_seller_blacklisted(username):
    """Vérifie si un vendeur est sur liste noire"""
    if not username:
        return False
    norm = normalize_seller_name(username)
    if not norm:
        return False
    blocked = load_blacklisted_sellers()
    return norm in blocked

def add_blacklisted_seller(username):
    """Ajoute un vendeur à la liste noire"""
    cleaned = normalize_seller_name(username)
    if not cleaned:
        return ""
    sellers = load_blacklisted_sellers()
    sellers.add(cleaned)
    save_blacklisted_sellers(sellers)
    log(f"⛔ Vendeur '{cleaned}' ajouté à la liste noire Vinted.")
    return cleaned

def remove_blacklisted_seller(username):
    """Retire un vendeur de la liste noire"""
    cleaned = normalize_seller_name(username)
    if not cleaned:
        return False
    sellers = load_blacklisted_sellers()
    if cleaned in sellers:
        sellers.remove(cleaned)
        save_blacklisted_sellers(sellers)
        log(f"✅ Vendeur '{cleaned}' retiré de la liste noire Vinted.")
        return True
    return False

def repair_mojibake(text):
    """Répare les caractères accentués corrompus en UTF-8 / latin-1 (ex: Ã© -> é, Ã¨ -> è)"""
    if not text:
        return ""
    mojibake_map = {
        'Ã©': 'é', 'Ã¨': 'è', 'Ãª': 'ê', 'Ã«': 'ë',
        'Ã ': 'à', 'Ã¢': 'â', 'Ã®': 'î', 'Ã¯': 'ï',
        'Ã´': 'ô', 'Ã¶': 'ö', 'Ã¹': 'ù', 'Ã»': 'û',
        'Ã¼': 'ü', 'Ã§': 'ç', 'Ã‰': 'É', 'Ãˆ': 'È',
        'ÃŠ': 'Ê', 'Ã€': 'À', 'Ã‚': 'Â', 'ÃŽ': 'Î',
        'Ã”': 'Ô', 'Ã™': 'Ù', 'Ã›': 'Û', 'Ã‡': 'Ç',
        'cÅur': 'cœur', 'cÅ“ur': 'cœur', 'Å“': 'œ',
        'Â°': '°', 'Â«': '«', 'Â»': '»', 'â€™': "'",
        'â€“': '-', 'â€”': '-', 'â€¦': '...',
        'Ãtienne': 'Étienne', 'Ãtat': 'État', 'Ã ': 'à '
    }
    for bad, good in mojibake_map.items():
        text = text.replace(bad, good)
    return text

def clean_text(text):
    """Nettoyage radical des parasites Vinted et réparation des accents"""
    if not text: return ""
    import re
    text = repair_mojibake(text)
    # Supprime les badges publicitaires et parasites
    text = re.sub(r'(?i)enlevé\s*!?', '', text)
    text = re.sub(r'(?i)nouveau\s*!?', '', text)
    text = re.sub(r'\s+', ' ', text)
    return text.strip()

def is_excluded_size(size_str, title_str="", desc_str=""):
    """
    Filtre les tailles enfants (âges, cm, mots-clés) ainsi que XS et S.
    Conserve les tailles adultes M, L, XL, XXL+, tailles uniques et N/A non identifiés comme enfant.
    """
    import re
    s = (size_str or "").strip().upper()
    t = (title_str or "").strip().lower()

    # 1. Détection des tailles enfants
    # Mots-clés dans la taille (ex: '10 ans', '12 ans', '14 ans / 164 cm', '6 mois')
    child_size_keywords = ['ans', 'mois', 'yr', 'year', 'anni', 'anos', 'enfant', 'kid', 'junior', 'jr', 'cm']
    if any(k in s.lower() for k in child_size_keywords):
        return True, f"Taille enfant ({size_str})"

    # Mots-clés enfants dans le titre (ex: 'Maillot ASSE Enfant 10 ans')
    if any(re.search(rf'\b{re.escape(kw)}\b', t) for kw in ['enfant', 'enfants', 'kids', 'junior', 'bebe', 'bébé', 'garcon', 'garçon', 'fille', 'baby', 'youth']):
        return True, "Mot-clé enfant dans le titre"

    # Âge enfant dans le titre (ex: '10 ans', '8a', '12 ans')
    if re.search(r'\b\d{1,2}\s*(?:ans|a|mois|m|years|yrs)\b', t):
        return True, "Âge enfant dans le titre"

    # Tailles jeunesse internationales type YXS, YS, YM, YL, YXL
    if re.match(r'^Y[SMLX]+$', s):
        return True, f"Taille Youth ({size_str})"

    # Tailles en cm (ex: 128, 140, 152, 164 cm)
    if re.search(r'\b(1[0-7][0-9])\s*cm\b', s.lower()) or re.search(r'\b(1[0-7][0-9])\s*cm\b', t):
        return True, "Taille en cm (enfant)"

    # Tailles numériques enfant pures (tailles standards Vinted enfant)
    if re.match(r'^(104|110|116|122|128|134|140|146|152|158|164|170|176)$', s):
        return True, f"Taille numérique enfant ({size_str})"

    # 2. Exclusion des tailles XS et S
    # Strictement XS, XXS, XXXS
    if re.match(r'^(X{1,3}S|EXTRA\s*SMALL)$', s):
        return True, f"Taille XS ({size_str})"

    # Strictement S
    if re.match(r'^(S|SMALL)$', s):
        return True, f"Taille S ({size_str})"

    # Combinaison type XS/S ou S/XS
    if re.match(r'^(XS\s*/\s*S|S\s*/\s*XS)$', s):
        return True, f"Taille XS/S ({size_str})"

    if re.match(r'^(32|34|36)(?:\s*/\s*(?:XS|S))?$', s) or re.match(r'^(?:XS|S)\s*/\s*(32|34|36)$', s):
        return True, f"Taille numérique XS/S ({size_str})"

    return False, "OK"

def parse_price(price_str):
    """Extrait la valeur numérique flottante d'un prix (ex: '35.00 €' -> 35.0)"""
    if not price_str: return None
    import re
    m = re.search(r'(\d+[\d\s]*(?:[.,]\d+)?)', str(price_str))
    if m:
        num_str = m.group(1).replace(' ', '').replace(',', '.')
        try: return float(num_str)
        except ValueError: return None
    return None

def is_excluded_product(title_str="", desc_str="", price_str=""):
    """
    Filtre les articles indésirables avec zéro faux positif sur les vrais maillots :
    1. Plafond de prix à 350 € max
    2. Mugs, tasses, bols, chopes
    3. Cartes Panini, stickers, vignettes, topps
    4. Magnets, magnettes, aimants
    """
    import re
    t = (title_str or "").lower()
    d = (desc_str or "").lower()

    # 1. Plafond de prix : max 350 € (strictement supérieur à 350€)
    pval = parse_price(price_str)
    if pval is not None and pval > 350.0:
        return True, f"Prix supérieur à 350€ ({pval:.2f}€)"

    # 2. Mugs / Tasses / Bols / Chopes
    mug_pattern = r'\b(mug|mugs|tasse|tasses|bol|bols|chope|chopes)\b'
    if re.search(mug_pattern, t):
        return True, "Mug / Tasse"
    if d and re.search(mug_pattern, d):
        if not re.search(r'\b(maillot|jersey|veste|tenue|ensemble)\b', t):
            return True, "Mug / Tasse"

    # 3. Panini / Stickers / Vignettes / Topps / Trading cards
    card_pattern = r'\b(panini|sticker|stickers|vignette|vignettes|topps|adrenalyn|trading\s*cards?)\b'
    if re.search(card_pattern, t):
        return True, "Panini / Sticker"
    if d and re.search(card_pattern, d):
        if not re.search(r'\b(maillot|jersey|veste|tenue|ensemble)\b', t):
            return True, "Panini / Sticker"

    # 4. Cartes seules : si le titre concerne des cartes de collection (sans mention de maillot/jersey)
    if re.search(r'\b(carte|cartes)\b', t):
        # Exclut si pas de mention de vêtement, ou si spécifié carte de collection/panini
        if not re.search(r'\b(maillot|jersey|veste|tenue|ensemble)\b', t) or re.search(r'\b(carte[s]?\s+panini|carte[s]?\s+collector|carte[s]?\s+postale[s]?)\b', t):
            return True, "Carte de collection"

    # 5. Magnets / Magnettes / Aimants
    magnet_pattern = r'\b(magnets?|magnettes?|aimants?|aimant[ée]s?)\b'
    if re.search(magnet_pattern, t):
        return True, "Magnet / Aimant"
    if d and re.search(magnet_pattern, d):
        # Si le titre ne mentionne pas explicitement un maillot/vêtement de sport, ou si la description décrit des magnets
        if not re.search(r'\b(maillot|jersey|veste|tenue|ensemble|surv[eê]tement|short)\b', t) or re.search(r'\b(lot\s+de\s+magnets?|magnets?\s+aimant[ée]s?|aimant\s+de\s+frigo)\b', d):
            return True, "Magnet / Aimant"

    # 6. Vestes, blousons, doudounes, parkas, coupe-vents
    jacket_pattern = r'\b(veste|vestes|blouson|blousons|doudoune|doudounes|parka|parkas|coupe[- ]vent|k[- ]?way|anorak)\b'
    if re.search(jacket_pattern, t):
        if not re.search(r'\b(maillot|jersey)\b', t):
            return True, "Veste / Blouson"
    if d and re.search(jacket_pattern, d):
        if not re.search(r'\b(maillot|jersey)\b', t):
            return True, "Veste / Blouson"

    return False, "OK"

def is_asse_jersey_match(title):
    """Filtrage strict ASSE avec limites de mots (évite les faux positifs type Borussia/Strasbourg tout en capturant tous les produits ASSE/St-Etienne)"""
    if not title: return False
    import re
    title_low = title.lower()
    team_pattern = r'\b(asse|saint[- \.]*etienne|st[- \.]*etienne|sainté|saint[- \.]*étienne|st[- \.]*étienne)\b'
    return bool(re.search(team_pattern, title_low))

def get_api_search_url(query, color_id=None):
    """Génère l'URL d'API directe Vinted pour une recherche texte"""
    url = f"https://www.vinted.fr/api/v2/catalog/items?search_text={quote_plus(query)}&order=newest_first&page=1&per_page=48"
    if color_id:
        url += f"&color_ids[]={color_id}"
    return url

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

def get_search_url(query, color_id=None):
    url = f"https://www.vinted.fr/catalog?search_text={query.replace(' ', '+')}&order=newest_first"
    if color_id:
        url += f"&color_ids[]={color_id}"
    return url

def log(message):
    """Log avec timestamp heure de Paris et persistance automatique des erreurs"""
    timestamp = get_paris_time().strftime('%Y-%m-%d %H:%M:%S')
    formatted = f"[{timestamp}] {message}"
    print(formatted, flush=True)

    if any(k in message for k in ["⚠️", "🚨", "❌", "Erreur", "erreur", "Error", "error", "Timeout", "timeout", "WATCHDOG", "Incident", "incident"]):
        try:
            with open(ERRORS_LOG_FILE, "a", encoding="utf-8") as f:
                f.write(formatted + "\n")
        except Exception:
            pass

def load_last_seen_id():
    """Charge le dernier ID vu depuis le fichier"""
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r") as f:
                return int(f.read().strip())
        except:
            pass
    return 0

def save_last_seen_id(item_id):
    """Sauvegarde le dernier ID vu"""
    with open(STATE_FILE, "w") as f:
        f.write(str(item_id))

def load_seen_ids_cache():
    """Charge l'historique persistant des IDs déjà traités pour éviter tout doublon après redémarrage"""
    seen = set()
    if os.path.exists(SEEN_IDS_FILE):
        try:
            with open(SEEN_IDS_FILE, "r") as f:
                data = json.load(f)
                if isinstance(data, list):
                    for x in data:
                        try:
                            seen.add(int(x))
                        except (ValueError, TypeError):
                            pass
            log(f"💾 [Cache] {len(seen)} IDs déjà vus chargés depuis {SEEN_IDS_FILE}")
        except Exception as e:
            log(f"⚠️ Erreur chargement cache IDs vus: {e}")
    return seen

def save_seen_ids_cache(seen_set):
    """Sauvegarde les 3000 derniers IDs vus sur disque"""
    try:
        recent_ids = sorted(list(seen_set), reverse=True)[:3000]
        with open(SEEN_IDS_FILE, "w") as f:
            json.dump(recent_ids, f)
    except Exception as e:
        log(f"⚠️ Erreur sauvegarde cache IDs vus: {e}")

def load_alerted_ids_cache():
    """Charge la liste des IDs ayant déjà reçu une alerte Discord (garantie absolue anti-doublon)"""
    alerted = set()
    if os.path.exists(ALERTED_IDS_FILE):
        try:
            with open(ALERTED_IDS_FILE, "r") as f:
                data = json.load(f)
                if isinstance(data, list):
                    for x in data:
                        try:
                            alerted.add(int(x))
                        except (ValueError, TypeError):
                            pass
            log(f"💾 [Cache Alertes] {len(alerted)} annonces déjà alertées chargées depuis {ALERTED_IDS_FILE}")
        except Exception as e:
            log(f"⚠️ Erreur chargement cache alertes: {e}")
    return alerted

def save_alerted_ids_cache(alerted_set):
    """Sauvegarde les 3000 derniers IDs alertés sur disque pour résister aux redémarrages"""
    try:
        recent_ids = sorted(list(alerted_set), reverse=True)[:3000]
        with open(ALERTED_IDS_FILE, "w") as f:
            json.dump(recent_ids, f)
    except Exception as e:
        log(f"⚠️ Erreur sauvegarde cache alertes: {e}")

def load_filet_seen_ids_cache():
    """Charge l'historique des IDs déjà vus par le Filet de sécurité"""
    seen = set()
    if os.path.exists(FILET_SEEN_IDS_FILE):
        try:
            with open(FILET_SEEN_IDS_FILE, "r") as f:
                data = json.load(f)
                if isinstance(data, list):
                    for x in data:
                        try:
                            seen.add(int(x))
                        except (ValueError, TypeError):
                            pass
            log(f"💾 [Cache Filet] {len(seen)} IDs déjà vus chargés depuis {FILET_SEEN_IDS_FILE}")
        except Exception as e:
            log(f"⚠️ Erreur chargement cache Filet: {e}")
    return seen

def save_filet_seen_ids_cache(seen_set):
    """Sauvegarde les 3000 derniers IDs vus par le Filet sur disque"""
    try:
        recent_ids = sorted(list(seen_set), reverse=True)[:3000]
        with open(FILET_SEEN_IDS_FILE, "w") as f:
            json.dump(recent_ids, f)
    except Exception as e:
        log(f"⚠️ Erreur sauvegarde cache Filet: {e}")

def fetch_item_description(item_url):
    """Récupère rapidement la description d'une annonce via une mini-requête HTTP (< 0.3s)"""
    if not item_url:
        return ""
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept-Language': 'fr-FR,fr;q=0.9',
        }
        resp = requests.get(item_url, headers=headers, timeout=4)
        if resp.status_code == 200:
            resp.encoding = 'utf-8'
            html = resp.text
            desc_raw = ""
            m_json = re.search(r'\"description\":\"(.*?)\"', html)
            if m_json:
                raw_val = m_json.group(1)
                def unescape_u(m):
                    try:
                        return chr(int(m.group(1), 16))
                    except Exception:
                        return m.group(0)
                desc_raw = re.sub(r'\\u([0-9a-fA-F]{4})', unescape_u, raw_val)
                desc_raw = desc_raw.replace('\\n', '\n').replace('\\r', '').replace('\\"', '"').replace('\\/', '/').replace('\\\\', '\\')
            if not desc_raw:
                m_dom = re.search(r'itemprop=\"description\"[^>]*>(.*?)</div>', html, re.DOTALL)
                if m_dom:
                    desc_raw = re.sub(r'<[^>]+>', '', m_dom.group(1)).strip()
            return clean_text(desc_raw)
    except Exception as e:
        log(f"⚠️ [Vinted] Erreur micro-fetch description: {e}")
    return ""

def scrape_item_details(page, item_url):
    """Va sur la page de l'article pour récupérer infos détaillées via API interne (V3.0 API Call)"""
    try:
        log(f"🔎 Scraping détails: {item_url}")
        
        # Extraire l'ID de l'item depuis l'URL
        import re
        id_match = re.search(r'/items/(\d+)', item_url)
        item_id = id_match.group(1) if id_match else None
        
        if not item_id:
            log("❌ Impossible d'extraire l'ID de l'URL")
            return {"description": "", "photos": [], "brand": "N/A", "size": "N/A", "status": "N/A"}

        # On va sur une page "neutre" (la page d'accueil ou la recherche) pour avoir le contexte de session
        # Pas besoin d'aller sur la page détail lourde, on peut juste fetch l'API
        # Mais pour être sûr d'avoir les cookies, restons sur la page actuelle ou allons sur la home
        # Si on est déjà dans un contexte ouvert, on peut juste faire fetch
        # Le contexte appelant ouvre déjà une page vide, allons sur Vinted Home pour initialiser la session si besoin
        # page.goto("https://www.vinted.fr", wait_until='domcontentloaded') 
        # (Optimisation: on suppose qu'on a déjà les cookies de la recherche précédente)
        
        # Pour être sûr, on va quand même sur la page de l'item (ça génère les cookies spécifiques item)
        page.goto(item_url, wait_until='domcontentloaded', timeout=22000)

        # Récupération de TOUTES les photos haute résolution (/f800/) depuis les scripts Next.js ou le DOM
        photos = page.evaluate("""() => {
            const photos = [];
            const scripts = document.querySelectorAll('script');
            scripts.forEach(s => {
                const txt = s.textContent || '';
                const parts = txt.split('https://images1.vinted.net/');
                for (let i = 1; i < parts.length; i++) {
                    const urlPart = parts[i].split('"')[0].split('\\\\')[0];
                    if (urlPart.includes('/f800/')) {
                        photos.push('https://images1.vinted.net/' + urlPart);
                    }
                }
            });
            if (photos.length > 0) return Array.from(new Set(photos));
            
            const imgs = Array.from(document.querySelectorAll('img'))
                                 .map(i => i.src || i.getAttribute('data-src') || '')
                                 .filter(s => s && s.includes('vinted.net') && (s.includes('/f800/') || s.includes('/full/') || s.includes('/1500/')));
            return Array.from(new Set(imgs));
        }""")
        photos = list(dict.fromkeys(photos))

        # APPEL API DIRECT via le navigateur
        log(f"📡 Appel API interne pour l'item {item_id}...")
        api_data = page.evaluate(f"""async () => {{
            try {{
                const response = await fetch('/api/v2/items/{item_id}?localize=false', {{
                    headers: {{
                        'Accept': 'application/json, text/plain, */*'
                    }}
                }});
                if (response.ok) {{
                    return await response.json();
                }}
                return null;
            }} catch (e) {{
                return null;
            }}
        }}""")
        
        description = ""
        brand = "N/A"
        size = "N/A"
        status = "N/A"
        
        if api_data and 'item' in api_data:
            item = api_data['item']
            log("✅ Réponse API reçue !")
            
            description = item.get('description', '')
            brand = item.get('brand_title', 'N/A')
            size = item.get('size_title', 'N/A')
            status = item.get('status', 'N/A') # Parfois c'est status_id, il faut mapper, mais essayons title
            
            # Si status est vide, parfois c'est pas envoyé
            if status == 'N/A' and 'status' in item:
                 # Vinted API change parfois
                 pass
            
        else:
            log("⚠️ API Vinted muette ou erreur")

        # Si l'API n'a pas tout renvoyé ou a échoué, on extrait depuis les scripts / le DOM de la page
        if not description or brand == 'N/A' or size == 'N/A' or status in ['N/A', 'Non spécifié']:
            try:
                dom_details = page.evaluate("""() => {
                    let dBrand = 'N/A', dSize = 'N/A', dStatus = 'N/A', dDesc = '';
                    
                    const descEl = document.querySelector('[itemprop="description"]');
                    if (descEl) dDesc = descEl.innerText.trim();

                    // Recherche dans les scripts Next.js (hydratation JSON)
                    try {
                        const scripts = Array.from(document.querySelectorAll('script'));
                        for (const s of scripts) {
                            const txt = s.textContent || '';
                            if (txt.includes('code') && (txt.includes('size') || txt.includes('brand') || txt.includes('status'))) {
                                if (dSize === 'N/A') {
                                    const m = txt.match(/["\\\\]+code["\\\\]+:\s*["\\\\]+size["\\\\]+.*?["\\\\]+value["\\\\]+:\s*["\\\\]+([^"\\\\]+)["\\\\]+/);
                                    if (m) dSize = m[1].trim();
                                }
                                if (dStatus === 'N/A') {
                                    const m = txt.match(/["\\\\]+code["\\\\]+:\s*["\\\\]+status["\\\\]+.*?["\\\\]+value["\\\\]+:\s*["\\\\]+([^"\\\\]+)["\\\\]+/);
                                    if (m) dStatus = m[1].trim();
                                }
                                if (dBrand === 'N/A') {
                                    const m = txt.match(/["\\\\]+code["\\\\]+:\s*["\\\\]+brand["\\\\]+.*?["\\\\]+title["\\\\]+:\s*["\\\\]+([^"\\\\]+)["\\\\]+/);
                                    if (m) dBrand = m[1].trim();
                                }
                            }
                        }
                    } catch (e) {}

                    // Recherche dans les éléments DOM
                    if (dSize === 'N/A' || dBrand === 'N/A' || dStatus === 'N/A') {
                        const items = document.querySelectorAll('.details-list__item, [data-testid*="item-attributes"]');
                        items.forEach(el => {
                            const t = el.innerText || '';
                            const valEl = el.querySelector('.details-list__item-value, [data-testid*="value"]');
                            const val = valEl ? valEl.innerText.trim() : '';
                            if (val) {
                                if (/taille|size/i.test(t) && dSize === 'N/A') dSize = val;
                                if (/marque|brand/i.test(t) && dBrand === 'N/A') dBrand = val;
                                if (/état|status|condition/i.test(t) && dStatus === 'N/A') dStatus = val;
                            }
                        });
                    }

                    return { description: dDesc, brand: dBrand, size: dSize, status: dStatus };
                }""")
                if not description and dom_details.get('description'):
                    description = dom_details['description']
                if brand == 'N/A' and dom_details.get('brand') != 'N/A':
                    brand = dom_details['brand']
                if size == 'N/A' and dom_details.get('size') != 'N/A':
                    size = dom_details['size']
                if status in ['N/A', 'Non spécifié'] and dom_details.get('status') not in ['N/A', 'Non spécifié']:
                    status = dom_details['status']
            except Exception as e:
                log(f"⚠️ Erreur fallback DOM/Scripts item: {e}")
        
        log(f"✅ Détails finaux: {brand} | {size} | {status}")
        
        return {
            "description": description,
            "photos": photos,
            "brand": brand,
            "size": size,
            "status": status
        }
    except Exception as e:
        log(f"⚠️ Erreur scraping détails (API Mode): {e}")
        return {"description": "", "photos": [], "brand": "N/A", "size": "N/A", "status": "N/A"}

def fetch_direct_catalog_api(page, api_url):
    """Interroge directement l'API catalogue Vinted via fetch() dans le navigateur"""
    try:
        data = page.evaluate(f"""async () => {{
            try {{
                const res = await fetch('{api_url}', {{
                    headers: {{ 'Accept': 'application/json, text/plain, */*' }}
                }});
                if (res.status === 429) return {{ rate_limited: true, status: 429 }};
                if (res.status === 401 || res.status === 403) return {{ auth_error: true, status: res.status }};
                if (res.ok) return await res.json();
                return null;
            }} catch(e) {{
                return null;
            }}
        }}""")
        if not data:
            return []
        
        if isinstance(data, dict):
            if data.get('rate_limited'):
                log("⚠️ Vinted Rate Limit (429) détecté ! Pause de sécurité de 90s...")
                time.sleep(90)
                return []
            if data.get('auth_error'):
                log(f"⚠️ Erreur statut Vinted ({data.get('status')}). Pause courte...")
                time.sleep(5)
                return []

        if 'items' not in data:
            return []
        
        items = []
        for raw in data.get('items', []):
            try:
                item_id = raw.get('id')
                if not item_id: continue
                title = raw.get('title') or ''
                price_data = raw.get('price')
                if isinstance(price_data, dict):
                    price = f"{price_data.get('amount', 'N/A')} €"
                elif price_data is not None:
                    price = f"{price_data} €"
                else:
                    price = 'N/A'
                
                size = raw.get('size_title') or 'N/A'
                brand = raw.get('brand_title') or 'N/A'
                status = raw.get('status') or 'Non spécifié'
                url = raw.get('url') or f"https://www.vinted.fr/items/{item_id}"
                
                photo = ''
                if raw.get('photo') and isinstance(raw['photo'], dict):
                    photo = raw['photo'].get('url', '')
                
                items.append({
                    'id': item_id,
                    'title': title,
                    'price': price,
                    'size': size,
                    'brand': brand,
                    'status': status,
                    'url': url,
                    'photo': photo
                })
            except Exception:
                pass
        return items
    except Exception as e:
        log(f"⚠️ Erreur fetch API catalogue direct: {e}")
        return []

def extract_items_from_page(page):
    """Extrait les articles avec Parsing Intelligent du Titre (V5.0)"""
    try:
        page.wait_for_selector('div[data-testid*="item"]', timeout=10000)
        
        items = page.evaluate("""
            () => {
                const items = [];
                const itemElements = document.querySelectorAll('div[data-testid*="item"], div[class*="feed-grid__item"]');
                
                itemElements.forEach((el) => {
                    try {
                        const link = el.querySelector('a');
                        if (!link) return;
                        
                        const url = link.href;
                        const idMatch = url.match(/items\\/(\\d+)/);
                        if (!idMatch) return;
                        const itemId = parseInt(idMatch[1]);
                        
                        // RECUPERATION DU TITRE COMPLET (contient souvent marque, taille, état)
                        let rawTitle = link.getAttribute('title') || '';
                        if (!rawTitle) {
                             const img = el.querySelector('img');
                             if (img) rawTitle = img.alt;
                        }
                        
                        // Valeurs par défaut
                        let price = 'N/A';
                        let size = 'N/A';
                        let brand = 'N/A';
                        let status = 'Non spécifié';
                        let title = rawTitle; // Par défaut on prend tout

                        // ANALYSE DU TITRE (Parsing V9.0 - Insensible à la casse)
                        // Exemple: "Veste ASSE, Marque: Le Coq Sportif, État: Très bon état, Taille: M, 15.00 €, 16.45 €"
                        const hasMeta = /(?:marque|brand|taille|size|taglia|talla|état|etat|condition)\s*:/i.test(rawTitle);
                        if (hasMeta) {
                            // Nettoyage du titre réel : on retire la chaîne de métadonnées Vinted
                            const cleanT = rawTitle.replace(/,\s*(?:marque|brand|taille|size|taglia|talla|état|etat|condition)\s*:.*$/i, '').trim();
                            if (cleanT) title = cleanT;
                            
                            // Extraction par Regex JS insensible à la casse
                            const brandMatch = rawTitle.match(/(?:marque|brand|marca|marke)\s*:\s*([^,]+)/i);
                            if (brandMatch) brand = brandMatch[1].trim();
                            
                            const sizeMatch = rawTitle.match(/(?:taille|size|taglia|talla|maat)\s*:\s*([^,]+)/i);
                            if (sizeMatch) size = sizeMatch[1].trim();
                            
                            const statusMatch = rawTitle.match(/(?:état|etat|condition|stato|estado)\s*:\s*([^,]+)/i);
                            if (statusMatch) status = statusMatch[1].trim();

                            const priceMatch = rawTitle.match(/,\s*(\d+(?:[.,]\d+)?\s*€)/i);
                            if (priceMatch) price = priceMatch[1].trim();
                        }
                        
                        // Récupération de TOUS les textes (morceaux + bloc complet)
                        const texts = Array.from(el.querySelectorAll('p, h3, h4, span, div'))
                                           .map(e => e.innerText.trim())
                                           .filter(t => t.length > 0);
                        
                        // On ajoute le texte brut complet de l'élément pour voir les lignes concaténées
                        texts.push(el.innerText.trim());
                        
                        const uniqueTexts = [...new Set(texts)];
                        
                        // Extraction d'un prix propre s'il manque ou est pollué
                        if (price === 'N/A' || price.length > 20 || price.includes('·') || price.includes('incl')) {
                            const priceRegex = /(\d+[\d\s]*[.,]\d{2}\s*€|\d+\s*€)/;
                            const pText = uniqueTexts.find(t => priceRegex.test(t));
                            if (pText) {
                                const m = pText.match(priceRegex);
                                if (m) price = m[1].trim();
                            } else {
                                price = uniqueTexts.find(t => t.includes('€') || t.includes('$')) || 'N/A';
                            }
                        }
                        
                        // Si la taille est encore N/A, on tente l'heuristique avancée sur uniqueTexts
                        if (size === 'N/A') {
                            const sizeRegex = /^(XS|S|M|L|XL|XXL|XXXL|[0-9]{1,3}(?:\s*ans)?|Unique|[0-9]{2}\s*\/\s*[0-9]{2})$/i;
                            for (const t of uniqueTexts) {
                                if (t.includes('€') || t.includes('$')) continue;
                                if (sizeRegex.test(t)) {
                                    size = t;
                                    break;
                                }
                                // Découpage des éléments composites comme "M · Très bon état"
                                const parts = t.split(/[·•|]/).map(p => p.trim());
                                for (const p of parts) {
                                    if (sizeRegex.test(p)) {
                                        size = p;
                                        break;
                                    }
                                }
                                if (size !== 'N/A') break;
                            }
                        }

                        // 4. Heuristique "État" ULTIME (V6.3)
                        if (status === 'Non spécifié') {
                            const statusKeywords = [
                                "neuf avec étiquette", "neuf sans étiquette", "neuf",
                                "très bon état", "très bon", "bon état", "satisfaisant", 
                                "jamais porté", "porté"
                            ];
                            const stateText = uniqueTexts.find(t => 
                                statusKeywords.some(kw => t.toLowerCase().includes(kw))
                            );
                            if (stateText) {
                                const lowState = stateText.toLowerCase();
                                const found = statusKeywords.find(kw => lowState.includes(kw));
                                if (found) {
                                    status = found.charAt(0).toUpperCase() + found.slice(1);
                                }
                            }
                        }

                        // 5. Heuristique "Marque" de secours (V6.3 Ultra-Strict)
                        if (brand === 'N/A' || brand.toLowerCase().includes('enlevé')) {
                             const ignored = ['vinted', 'enlevé', 'nouveau', 'neuf', '€', 'recommandé', 'boosté', 'protection', 'avis', 'favori'];
                             const potentialBrand = uniqueTexts.find(t => {
                                 const low = t.toLowerCase();
                                 if (t.length < 2 || t.length > 25) return false;
                                 if (ignored.some(i => low.includes(i))) return false;
                                 if (/(neuf|état|porté|taille|size)/i.test(low)) return false;
                                 if (/^(XS|S|M|L|XL|XXL|[0-9]{2})$/i.test(t)) return false;
                                 if (t.includes('€')) return false;
                                 return true;
                             });
                             if (potentialBrand) brand = potentialBrand;
                        }

                        // 6. Nettoyage final du Titre (V8.2 AGRESSIF)
                        title = title.replace(/enlevé/gi, '').replace(/nouveau/gi, '').replace(/!/g, '').replace(/\\s*,\\s*$/, '').trim();
                        title = title.replace(/\\s{2,}/g, ' ');
                        if (!title || title.length < 3) title = 'Maillot ASSE';

                        const imgEl = el.querySelector('img');
                        const photo = imgEl?.src || '';

                        let seller = '';
                        const userLink = el.querySelector('a[href*="/member/"]');
                        if (userLink) {
                            const uMatch = userLink.href.match(/\/member\/\d+-?([^\/?#]+)?/);
                            if (uMatch && uMatch[1]) seller = uMatch[1];
                            else seller = userLink.innerText.trim();
                        }
                        
                        items.push({
                            id: itemId,
                            title: title,
                            price: price,
                            size: size,
                            brand: brand,
                            status: status,
                            url: url,
                            photo: photo,
                            seller: seller
                        });

                    } catch (e) {
                         // Silent
                    }
                });
                return items;
            }
        """)
        return items
    except Exception as e:
        log(f"❌ Erreur extraction liste: {e}")
        return []

def send_discord_alert(context, item):
    """Envoie une alerte Discord ultra-rapide (~0.3s) avec description Garmin et jusqu'à 10 photos HD dès le 1er envoi"""
    if not DISCORD_WEBHOOK_URL: return

    global alerted_ids
    raw_id = item.get('id')
    try:
        int_id = int(raw_id)
    except (ValueError, TypeError):
        int_id = raw_id

    # VERROU ABSOLU ANTI-DOUBLON (Empêche strictement 2 alertes pour le même item ID)
    with state_lock:
        if int_id and int_id in alerted_ids:
            log(f"🛡️ [Anti-Doublon Absolu] Alerte déjà envoyée pour #{int_id}, envoi bloqué !")
            return
        if int_id:
            alerted_ids.add(int_id)
            save_alerted_ids_cache(alerted_ids)

    try:
        import re

        price_raw = item.get('price', 'N/A')
        brand_raw = item.get('brand', 'N/A')
        size_raw = item.get('size', 'N/A')
        status_raw = item.get('status', 'Non spécifié')
        photo_url = item.get('photo', '')
        item_id = int_id
        item_url = item.get('url', f"https://www.vinted.fr/items/{item_id}")

        # Nettoyage radical du titre
        raw_title_val = clean_text(item.get('title'))
        clean_title = re.sub(r',\s*(?:marque|brand|taille|size|taglia|talla|état|etat|condition)\s*:.*$', '', raw_title_val, flags=re.IGNORECASE)
        clean_title = re.sub(r'\s*·.*$', '', clean_title)
        clean_title = re.sub(r'\d+[,\.]\d+\s*€.*$', '', clean_title)
        clean_title = clean_title.strip()
        final_title = clean_title if clean_title else "Maillot ASSE"

        final_brand = clean_text(brand_raw)
        final_price = clean_text(price_raw)
        if '·' in final_price or 'incl' in final_price or len(final_price) > 20:
            p_match = re.search(r'(\d+[\d\s]*[.,]\d{2}\s*€|\d+\s*€)', final_price)
            if p_match:
                final_price = p_match.group(1).strip()

        final_size = clean_text(size_raw)
        final_status = clean_text(status_raw)

        # Fallback pour la taille si N/A depuis le titre
        if final_size == 'N/A':
            size_search = re.search(r'\btaille\s*[:\s]\s*([XSLM0-9/ ]+?)(?:\s+[a-z]{3,}|\s*[,;·\n]|\s*$)', raw_title_val, re.IGNORECASE)
            if size_search:
                cand = size_search.group(1).strip().upper()
                if cand and len(cand) <= 10:
                    final_size = cand

        # Filtrage des produits indésirables (Mug, Panini, Prix > 350€)
        is_excl, reason = is_excluded_product(final_title, '', final_price)
        if is_excl:
            log(f"🚫 [Vinted] Alerte filtrée ({reason}) : {final_title} ({final_price})")
            return

        # Filtrage des tailles enfants et XS/S
        if FILTER_ADULT_ONLY:
            is_excl, reason = is_excluded_size(final_size, raw_title_val)
            if is_excl:
                log(f"🚫 [Vinted] Alerte filtrée ({reason}) : {final_title} (Taille: {final_size})")
                return

        # Filtrage vendeur bloqué préalable
        if item.get('seller') and is_seller_blacklisted(item['seller']):
            log(f"🚫 [Vinted] Alerte bloquée : vendeur '{item['seller']}' dans la liste noire !")
            return

        # Micro-fetch ultra-rapide HTTP (200-300ms) pour récupérer description, photos HD et vendeur
        photos = [photo_url] if photo_url else []
        desc_clean = ""
        seller_name = item.get('seller', '')
        try:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Accept-Language': 'fr-FR,fr;q=0.9',
            }
            resp = requests.get(item_url, headers=headers, timeout=4)
            if resp.status_code == 200:
                resp.encoding = 'utf-8'
                html = resp.text

                # Récupération du pseudo vendeur
                m_user = re.search(r'\"login\":\"([^\"]+)\"', html)
                if m_user:
                    seller_name = clean_text(m_user.group(1))
                if not seller_name:
                    m_mem = re.search(r'href=[\"\']/member/\d+[^\"]*[\"\'][^>]*>.*?<span[^>]*>([^<]+)</span>', html, re.DOTALL)
                    if m_mem:
                        seller_name = clean_text(m_mem.group(1))
                if not seller_name:
                    m_av_alt = re.search(r'Image__circle[^>]*>.*?<img[^>]+alt=[\"\']([^\"\']+)[\"\']', html, re.DOTALL)
                    if m_av_alt and m_av_alt.group(1).strip():
                        seller_name = clean_text(m_av_alt.group(1))

                # Blocage immédiat si le vendeur est sur liste noire
                if seller_name and is_seller_blacklisted(seller_name):
                    log(f"🚫 [Vinted] Alerte bloquée : vendeur '{seller_name}' dans la liste noire !")
                    return

                # Détection et exclusion formelle de l'avatar de profil du vendeur
                avatar_sigs = set()
                for av in re.findall(r'Image__circle[^>]*>.*?<img[^>]+src=[\"\']([^\"\']+)[\"\']', html, re.DOTALL):
                    sig = av.split('/')[-1].split('.')[0].split('?')[0]
                    if sig: avatar_sigs.add(sig)
                for sq in re.findall(r'images1\.vinted\.net/[^\"\'\s]+/(?:100x100|150x150|50x50|20x20)/([^\"\'\s\.\?]+)', html):
                    avatar_sigs.add(sq)

                # Récupération de toutes les photos HD (/f800/) de l'annonce en excluant l'avatar
                raw_photos = re.findall(r'https://images1\.vinted\.net/[^\"\'\s]+\/f800\/[^\"\'\s]+', html)
                scraped_photos = []
                for p in raw_photos:
                    p_clean = p.split('"')[0].split("'")[0].split('\\')[0]
                    if not any(sig in p_clean for sig in avatar_sigs):
                        if p_clean not in scraped_photos:
                            scraped_photos.append(p_clean)
                if scraped_photos:
                    photos = scraped_photos

                # Récupération propre de la description (préservation des accents et emojis)
                desc_raw = ""
                m_json = re.search(r'\"description\":\"(.*?)\"', html)
                if m_json:
                    raw_val = m_json.group(1)
                    def unescape_u(m):
                        try:
                            return chr(int(m.group(1), 16))
                        except Exception:
                            return m.group(0)
                    desc_raw = re.sub(r'\\u([0-9a-fA-F]{4})', unescape_u, raw_val)
                    desc_raw = desc_raw.replace('\\n', '\n').replace('\\r', '').replace('\\"', '"').replace('\\/', '/').replace('\\\\', '\\')
                if not desc_raw:
                    m_dom = re.search(r'itemprop=\"description\"[^>]*>(.*?)</div>', html, re.DOTALL)
                    if m_dom:
                        desc_raw = re.sub(r'<[^>]+>', '', m_dom.group(1)).strip()
                desc_clean = clean_text(desc_raw)
                if desc_clean:
                    is_excl, reason = is_excluded_product(final_title, desc_clean, final_price)
                    if is_excl:
                        log(f"🚫 [Vinted] Alerte filtrée ({reason}) : {final_title} ({final_price})")
                        return
        except Exception as e:
            log(f"⚠️ [Vinted] Micro-fetch fiche produit: {e}")

        # Description formatée pour Discord embed avec bouton d'achat direct
        description_text = f"💰 **{final_price}** | 📏 Taille: **{final_size}**\n🏷️ Marque: **{final_brand}** | État: **{final_status}**"
        if seller_name:
            description_text += f"\n👤 Vendeur: **{seller_name}**"

        description_text += f"\n\n🛒 **[⚡ ACHETER SUR VINTED (CLIQUEZ ICI) ⚡]({item_url})**"

        if desc_clean:
            embed_desc_body = desc_clean[:350] + ("..." if len(desc_clean) > 350 else "")
            description_text += f"\n\n📝 *Description :*\n{embed_desc_body}"

        embed1 = {
            "title": f"🔔 {final_title}",
            "url": item_url,
            "description": description_text,
            "color": 0x09B83E,
            "fields": [
                {
                    "name": "⚡ Accès Rapide",
                    "value": f"👉 **[⚡ OUVRIR ET ACHETER IMMÉDIATEMENT ⚡]({item_url})**",
                    "inline": False
                }
            ],
            "footer": {"text": f"Vinted Sniper • ID: {item_id}"},
            "timestamp": datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S.%f')[:-3] + 'Z'
        }

        if photos:
            embed1["image"] = {"url": photos[0]}

        embeds_batch1 = [embed1]
        for photo_url_item in photos[1:10]:
            embeds_batch1.append({"url": item_url, "image": {"url": photo_url_item}})

        # TEXTE DE NOTIFICATION PUSH POUR MONTRE GARMIN / ÉCRAN VERROUILLÉ
        # Contient titre, prix, taille, marque ET l'extrait de description
        desc_preview = ""
        if desc_clean:
            desc_preview = desc_clean[:250].strip()
            if len(desc_clean) > 250:
                desc_preview += "..."

        notif_text = f"""@everyone | {final_title}
💰 {final_price} | 📏 {final_size} | 🏷️ {final_brand}"""
        if desc_preview:
            notif_text += f"\n📝 {desc_preview}"

        payload1 = {
            "content": notif_text,
            "username": "Vinted ASSE Bot", 
            "avatar_url": "https://images.vinted.net/assets/icon-76x76-precomposed-3e6e4c5f0b8c7e5a5c5e5e5e5e5e5e5e.png", 
            "embeds": embeds_batch1,
            "components": [
                {
                    "type": 1,
                    "components": [
                        {
                            "type": 2,
                            "style": 5,
                            "label": "⚡ Acheter sur Vinted",
                            "url": item_url
                        }
                    ]
                }
            ]
        }

        requests.post(DISCORD_WEBHOOK_URL, json=payload1, timeout=8)

        # Si l'annonce contient plus de 10 photos (jusqu'à 20 photos au total) :
        # Envoi d'un 2ème lot 100% silencieux (flags: 4096 SUPPRESS_NOTIFICATIONS - aucune notif ni vibration)
        if len(photos) > 10:
            embeds_batch2 = []
            for photo_url_item in photos[10:20]:
                embeds_batch2.append({"url": item_url, "image": {"url": photo_url_item}})
            if embeds_batch2:
                payload2 = {
                    "username": "Vinted ASSE Bot",
                    "avatar_url": "https://images.vinted.net/assets/icon-76x76-precomposed-3e6e4c5f0b8c7e5a5c5e5e5e5e5e5e5e.png",
                    "embeds": embeds_batch2,
                    "flags": 4096
                }
                requests.post(DISCORD_WEBHOOK_URL, json=payload2, timeout=6)

        log(f"✅ [Vinted] Alerte envoyée #{item_id} ({min(len(photos), 20)} photos certifiées, description Garmin incluse)")

    except Exception as e:
        log(f"❌ Erreur Discord: {e}")

def watchdog_handler(signum, frame):
    """Tue le bot si un cycle prend trop de temps (Freeze detection)"""
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    print(f"[{timestamp}] 🚨 WATCHDOG: Bot figé depuis trop longtemps ! Redémarrage forcé...", flush=True)
    os._exit(1) # Sortie brutale pour forcer Railway à relancer

state_lock = threading.RLock()
flux_seen_ids = load_seen_ids_cache()
filet_seen_ids = load_filet_seen_ids_cache()
alerted_ids = load_alerted_ids_cache()
initialized_sources = set()
shared_last_seen_id = load_last_seen_id()
if flux_seen_ids:
    shared_last_seen_id = max(shared_last_seen_id, max(flux_seen_ids))

def process_incoming_items_safe(items, source_label="Flux", is_initial=False):
    """Traite une liste d'articles récupérés de manière thread-safe (filtrage et alertes Discord)"""
    global flux_seen_ids, filet_seen_ids, alerted_ids, shared_last_seen_id, initialized_sources
    with state_lock:
        is_filet = "Filet" in source_label

        # Absorption automatique de l'historique lors du premier passage de chaque source
        if source_label not in initialized_sources or is_initial:
            initialized_sources.add(source_label)
            count_absorbed = 0
            for item in items:
                try:
                    i_id = int(item['id'])
                except (ValueError, TypeError):
                    continue
                if is_filet:
                    if i_id not in filet_seen_ids:
                        filet_seen_ids.add(i_id)
                        count_absorbed += 1
                else:
                    if i_id not in flux_seen_ids:
                        flux_seen_ids.add(i_id)
                        count_absorbed += 1
            if is_filet:
                save_filet_seen_ids_cache(filet_seen_ids)
            else:
                save_seen_ids_cache(flux_seen_ids)
                if items:
                    try:
                        shared_last_seen_id = max(shared_last_seen_id, max(int(x['id']) for x in items if str(x.get('id', '')).isdigit()))
                        save_last_seen_id(shared_last_seen_id)
                    except: pass
            log(f"📥 [{source_label}] {count_absorbed} annonce(s) existante(s) absorbée(s) à l'initialisation.")
            return

        new_found = []
        for item in items:
            try:
                item_id = int(item['id'])
            except (ValueError, TypeError):
                continue
            item['id'] = item_id

            # 1. Protection absolue : si déjà alerté sur Discord, on ignore immédiatement (zéro doublon)
            if item_id in alerted_ids:
                continue

            if is_filet:
                # Filet de sécurité : cache dédié
                if item_id not in filet_seen_ids:
                    # Protection stricte contre les annonces anciennes de fond de catalogue
                    if shared_last_seen_id == 0 or item_id > (shared_last_seen_id - 500000):
                        new_found.append(item)
                    filet_seen_ids.add(item_id)
            else:
                # Flux général
                if item_id not in flux_seen_ids:
                    if shared_last_seen_id == 0 or item_id > (shared_last_seen_id - 500000):
                        new_found.append(item)
                    flux_seen_ids.add(item_id)
        
        if not new_found:
            return
        
        # Sauvegarde persistante des IDs vus
        if is_filet:
            save_filet_seen_ids_cache(filet_seen_ids)
        else:
            save_seen_ids_cache(flux_seen_ids)

        log(f"🆕 [Vinted] {len(new_found)} nouvel/nouveaux article(s) détecté(s) ({source_label}) !")
        new_found.sort(key=lambda x: int(x['id']))
        
        for item in new_found:
            t_titre = item.get('title', 'Sans titre')
            t_prix = item.get('price', 'N/A')
            t_taille = item.get('size', 'N/A')
            item_id = item['id']
            item_url = item.get('url', f"https://www.vinted.fr/items/{item_id}")
            log(f"🆕 [Vinted] Détecté #{item_id} : '{t_titre}' ({t_prix} | {t_taille}) [{source_label}]")

            # Double vérification anti-doublon (au cas où alerté entre-temps)
            if item_id in alerted_ids:
                continue

            # Vérification vendeur bloqué dès la liste
            seller_val = item.get('seller')
            if seller_val and is_seller_blacklisted(seller_val):
                log(f"🚫 Article ignoré dès la liste (Vendeur bloqué @{seller_val}) : '{t_titre}'")
                continue

            # 1. Filtrage des produits indésirables (Mug, Panini, Prix > 350€, Vestes)
            is_excl, reason = is_excluded_product(t_titre, '', t_prix)
            if is_excl:
                log(f"🚫 Article ignoré dès la liste ({reason}) : '{t_titre}' ({t_prix})")
                continue

            # 2. Filtrage des tailles enfants et XS/S
            if FILTER_ADULT_ONLY and item.get('size') and item.get('size') != 'N/A':
                is_excl, reason = is_excluded_size(item['size'], item.get('title', ''))
                if is_excl:
                    log(f"🚫 Article ignoré dès la liste ({reason}) : '{item.get('title')}' (Taille: {item['size']})")
                    continue

            # 3. Correspondance ASSE
            matched = False
            # Test direct sur le titre (ultra-rapide pour Flux et Filet)
            if is_asse_jersey_match(t_titre):
                matched = True
                log(f"🎯 MATCH {source_label} : '{t_titre}' ({t_prix})")
            elif is_filet:
                # Si l'annonce vient du Filet et que le titre est générique (ex: 'Maillot de foot'),
                # on vérifie la description car Vinted l'a retournée suite à la recherche ASSE
                desc = fetch_item_description(item_url)
                if desc:
                    is_excl_d, reason_d = is_excluded_product(t_titre, desc, t_prix)
                    if is_excl_d:
                        log(f"🚫 Article ignoré après vérification description ({reason_d}) : '{t_titre}'")
                        continue
                    if is_asse_jersey_match(desc):
                        matched = True
                        log(f"🎯 MATCH {source_label} (Confirmé dans la description) : '{t_titre}' ({t_prix})")

            if matched:
                send_discord_alert(None, item)
        
        if not is_filet and new_found:
            shared_last_seen_id = max(shared_last_seen_id, max(int(x['id']) for x in new_found))
            save_last_seen_id(shared_last_seen_id)
        
        # Nettoyage cache IDs si trop volumineux
        if len(flux_seen_ids) > 5000:
            seen_ids_list = sorted(list(flux_seen_ids), reverse=True)
            flux_seen_ids = set(seen_ids_list[:3000])
        if len(filet_seen_ids) > 5000:
            filet_ids_list = sorted(list(filet_seen_ids), reverse=True)
            filet_seen_ids = set(filet_ids_list[:3000])

def safe_route_filter(route):
    """Bloque les images/médias lourds et les trackers publicitaires pour accélérer le chargement"""
    try:
        if route.request.resource_type in ["image", "stylesheet", "font", "media"]:
            route.abort()
            return
        url_low = route.request.url.lower()
        if any(trk in url_low for trk in ["google-analytics", "doubleclick", "facebook", "criteo", "datadog", "braze", "hotjar"]):
            route.abort()
            return
        route.continue_()
    except Exception:
        pass

def worker_turbo_sniper():
    """Moteur Turbo Sniper : Priorité 80% au Flux Football Direct (temps réel pur) + 20% Filet de Sécurité Mots-clés alternés"""
    # Flux combiné Temps Réel : Maillots (3267) + Hauts & T-shirts de sport (584)
    FOOTBALL_CATALOG_URL = "https://www.vinted.fr/catalog?catalog_ids[]=3267&catalog_ids[]=584&order=newest_first"
    
    # Filet de Sécurité resserré (rotation ultra-rapide en ~1 min)
    SAFETY_QUERIES = [
        ("Maillot Asse", get_search_url("Maillot Asse")),
        ("Maillot Saint-Etienne", get_search_url("Maillot Saint-Etienne")),
        ("Maillot St Etienne", get_search_url("Maillot St Etienne")),
    ]

    log("🚀 [Vinted] Démarrage du Moteur Turbo-Sniper (Priorité Foot Temps Réel + Filet Sécurité Alterné)")
    log("⚡ [Vinted] 4 Scans Foot Direct pour 1 Scan Filet Sécurité en rotation continue")
    log("📸 [Vinted] Support jusqu'à 20 photos HD avec notifications silencieuses")

    safety_index = 0
    is_initial_scan = True

    while True:
        paris_now = get_paris_time()
        if os.environ.get("ENABLE_NIGHT_MODE", "false").lower() == "true" and 1 <= paris_now.hour < 7:
            log(f"🌙 [Vinted] Veille de nuit ({paris_now.strftime('%H:%M:%S')}).")
            time.sleep(60)
            continue

        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(
                    headless=True,
                    args=CHROMIUM_ARGS
                )
                context = browser.new_context(
                    user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                    viewport={'width': 1280, 'height': 720},
                    locale='fr-FR',
                    timezone_id='Europe/Paris'
                )
                context.route("**/*", safe_route_filter)

                page = context.new_page()
                page.set_default_timeout(20000)

                session_start_time = time.time()
                cycle_count = 0

                while True:
                    cycle_count += 1
                    now = time.time()

                    paris_now = get_paris_time()
                    if os.environ.get("ENABLE_NIGHT_MODE", "false").lower() == "true" and 1 <= paris_now.hour < 7:
                        break

                    # Recyclage mémoire préventif toutes les 2h ou 1200 scans
                    if (now - session_start_time) > 7200 or cycle_count > 1200:
                        log("♻️ [Vinted] Recyclage préventif session Chromium...")
                        break

                    # Purge préventive de l'onglet tous les 40 scans
                    if cycle_count % 40 == 0:
                        try: page.close()
                        except: pass
                        try:
                            page = context.new_page()
                            page.set_default_timeout(20000)
                        except: pass

                    # Choix de la cible : 4 scans Foot pour 1 scan Filet de sécurité
                    if cycle_count % 5 == 0:
                        label, target_url = SAFETY_QUERIES[safety_index % len(SAFETY_QUERIES)]
                        safety_index += 1
                        scan_label = f"Filet '{label}'"
                    else:
                        target_url = FOOTBALL_CATALOG_URL
                        scan_label = "Flux Direct Foot"

                    try:
                        if hasattr(signal, "SIGALRM"):
                            signal.signal(signal.SIGALRM, watchdog_handler)
                            signal.alarm(120)

                        page.goto(target_url, wait_until='domcontentloaded', timeout=22000)
                        items = extract_items_from_page(page)
                        log(f"⚡ [Vinted] Scan {scan_label} : {len(items)} annonces")
                        if items:
                            process_incoming_items_safe(items, scan_label, is_initial=is_initial_scan)
                            if is_initial_scan and cycle_count >= 5:
                                is_initial_scan = False
                    except Exception as e:
                        log(f"⚠️ [Vinted] Erreur locale : {e}")
                        err_str = str(e).lower()
                        if any(k in err_str for k in ["crash", "closed", "destroyed", "timeout"]):
                            log("🔄 [Vinted] Recréation immédiate de l'onglet suite à incident/timeout...")
                            try: page.close()
                            except: pass
                            try:
                                page = context.new_page()
                                page.set_default_timeout(20000)
                            except:
                                break
                    finally:
                        if hasattr(signal, "SIGALRM"):
                            signal.alarm(0)

                    # Pause optimisée entre chaque scan (1.0s à 1.4s pour cadence ~4.5s)
                    time.sleep(random.uniform(1.0, 1.4))

                try: browser.close()
                except: pass
        except Exception as e:
            log(f"🚨 [Vinted] Incident navigateur : {e}. Redémarrage dans 6s...")
            time.sleep(6)

def run_bot():
    try:
        os.nice(10)
    except Exception:
        pass
    try:
        worker_turbo_sniper()
    except KeyboardInterrupt:
        log("\n⛔ [Vinted] Arrêt du bot demandé")
    finally:
        log("👋 [Vinted] Bot éteint proprement")

if __name__ == "__main__":
    run_bot()
