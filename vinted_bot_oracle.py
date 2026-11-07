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
import fcntl
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
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    _env_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
    if os.path.exists(_env_file):
        with open(_env_file) as _f:
            for _line in _f:
                _line = _line.strip()
                if _line and not _line.startswith("#") and "=" in _line:
                    _k, _v = _line.split("=", 1)
                    os.environ.setdefault(_k.strip(), _v.strip())

# Configuration des recherches
PRIORITY_QUERIES = ["Maillot Asse", "Maillot Saint-Etienne", "Maillot St Etienne"]
SECONDARY_QUERIES = ["Jersey Asse", "Jersey Saint-Etienne", "Maglia Asse", "Camiseta Asse", "Ensemble Asse", "Trikot Asse"]
# Liste combinée pour l'initialisation
SEARCH_QUERIES = PRIORITY_QUERIES + SECONDARY_QUERIES

DISCORD_WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL")
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")
STATE_FILE = "last_seen_id.txt"
SEEN_IDS_FILE = "seen_ids_cache.json"
ALERTED_IDS_FILE = "alerted_ids_cache.json"
FILET_SEEN_IDS_FILE = "filet_seen_ids_cache.json"
TRACKED_ITEMS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tracked_items.json")
ERRORS_LOG_FILE = os.environ.get("ERRORS_LOG_FILE", "/root/vinted_errors.log" if os.path.exists("/root/JerseyAlert") else "vinted_errors.log")
BLACKLIST_FILE = os.environ.get("BLACKLIST_FILE", os.path.join(os.path.dirname(os.path.abspath(__file__)), "blacklisted_sellers.json"))
BLACKLIST_KEYWORDS_FILE = os.environ.get("BLACKLIST_KEYWORDS_FILE", os.path.join(os.path.dirname(os.path.abspath(__file__)), "blacklisted_keywords.json"))
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

_keywords_cache = {"mtime": 0, "keywords": []}
def load_blacklisted_keywords():
    """Charge la liste des mots-clés bloqués personnalisés avec cache mtime ultra-rapide"""
    global _keywords_cache
    if not os.path.exists(BLACKLIST_KEYWORDS_FILE):
        return []
    try:
        mtime = os.path.getmtime(BLACKLIST_KEYWORDS_FILE)
        if mtime != _keywords_cache["mtime"]:
            with open(BLACKLIST_KEYWORDS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                _keywords_cache["keywords"] = sorted(list({str(k).strip().lower() for k in data if str(k).strip()}))
                _keywords_cache["mtime"] = mtime
        return _keywords_cache["keywords"]
    except Exception:
        return _keywords_cache.get("keywords", [])

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
        'Ãtienne': 'Étienne', 'Ãtat': 'État'
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

    # Détection XS/S dans le titre si la taille transmise est absente, générique ou non-adulte
    if s in ('', 'N/A', 'AUTRE', 'UNIQUE', 'TAILLE UNIQUE') or not s:
        if re.search(r'(?:\b(?:taille|size|t\.|gr(?:öße)?|taglia|talla)\s*[:\s=-]*\s*(?:x{1,3}s|s|small)\b|(?:^|[\s\-_/])(?:taille\s*)?(?:x{1,3}s|s)\s*$)', t, re.I):
            return True, "Taille XS/S détectée dans le titre"

    # 3. Exclusion des tailles supérieures à XXL (XXXL / 3XL et plus)
    if re.search(r'\b(?:X{3,}L|[3-9]XL)\b', s):
        return True, f"Taille supérieure à XXL ({size_str})"

    if re.search(r'\b(?:X{3,}L|[3-9]XL)\b', t, re.I):
        return True, "Taille supérieure à XXL dans le titre"

    if desc_str:
        d_low = desc_str.lower()
        if re.search(r'\b(?:taille\s*[:\s=-]*\s*(?:x{3,}l|[3-9]xl)|en\s+(?:x{3,}l|[3-9]xl))\b', d_low):
            return True, "Taille supérieure à XXL dans la description"
        # Si la taille Vinted est absente/générique, vérifier aussi XS/S et tailles enfants dans la description
        if s in ('', 'N/A', 'AUTRE', 'UNIQUE', 'TAILLE UNIQUE'):
            if re.search(r'\btaille\s*[:\s=-]*\s*(?:x{1,3}s|s|small|extra\s*small)\b', d_low):
                return True, "Taille XS/S détectée dans la description"
            if re.search(r'\btaille\s*[:\s=-]*\s*(?:\d{1,2}\s*ans|enfant|junior|1[0-6]\d\s*cm)\b', d_low):
                return True, "Taille enfant détectée dans la description"

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

def is_asse_jersey_match(title):
    """Filtrage strict ASSE avec limites de mots (capture ASSE, A.S.S.E, Saint-Étienne, Sainté, etc.)"""
    if not title: return False
    import re, unicodedata
    title_low = ''.join(c for c in unicodedata.normalize('NFD', title) if unicodedata.category(c) != 'Mn').lower()
    title_low = title_low.replace('’', "'")

    # Bloquer les expressions composées non-football avec 'sainte' (Sainte-Barbe, Sainte-Marie, etc.) ou Sainté-Lyon (trail)
    non_foot_sainte = r'\bsainte[- ](?:barbe|marie|luce|croix|maxime|genevieve|adresse|claire|anne|rose|foy|helene)\b'
    if re.search(non_foot_sainte, title_low) and not re.search(r'\b(asse|saint[- \.]*etienne|st[- \.]*etienne)\b', title_low):
        return False

    # Bloquer spécifiquement la course Sainté-Lyon / Saintélyon
    if re.search(r'\bsaint[eé][- ]?lyon\b', title_low) and not re.search(r'\b(asse|foot|football)\b', title_low):
        return False

    # Neutraliser les mentions adversaire où l'ASSE est seulement l'adversaire affronté (ex: 'Maillot Lyon contre ASSE')
    asse_opp_pattern = r'\b(?:contre|vs\.?|face\s+[àa]|oppos[eé][es]?\s+[àa]|match\s+contre|jou[eé]\s+contre|match\s+face\s+[àa])\s+(?:l[\'\s]*)?(?:equipe\s+de\s+)?(?:as\s+)?(?:saint[- \.]*etienne|asse|st[- \.]*etienne|sainte|verts?)\b'
    title_asse_clean = re.sub(asse_opp_pattern, ' ', title_low)

    team_pattern = r'\b(asse|saint[- \.]*etienne|st[- \.]*etienne|sainte|(?:maillot|jersey|tenue|t-?shirt)?\s*(?:des|les)\s+verts|peuple\s+vert|allez\s+les\s+verts)\b|(?:\b|^)a[\.\s\-]+s[\.\s\-]+s[\.\s\-]*e(?:\.|\b)'
    return bool(re.search(team_pattern, title_asse_clean))

# Dictionnaire des clubs majeurs pour identifier le "tag stuffing" (spam de mots-clés)
CLUB_PATTERNS = {
    'psg': r'\b(psg|paris\s+sg|paris\s+saint[- ]germain)\b',
    'om': r'\b(om|olympique\s+de\s+marseille|marseille)\b',
    'ol': r'\b(ol|olympique\s+lyonnais|lyon)\b',
    'lens': r'\b(rc\s+lens|lens|rcl)\b',
    'lille': r'\b(losc|lille)\b',
    'monaco': r'\b(as\s+monaco|monaco|asm)\b',
    'rennes': r'\b(stade\s+rennais|rennes|srfc)\b',
    'nantes': r'\b(fc\s+nantes|nantes|fcn)\b',
    'nice': r'\b(ogc\s+nice|nice\s+ogc|ogcn|nice)\b',
    'bordeaux': r'\b(girondins|bordeaux|fcgb)\b',
    'montpellier': r'\b(mhsc|mshc|montpellier)\b',
    'strasbourg': r'\b(rcsa|strasbourg)\b',
    'toulouse': r'\b(tfc|toulouse)\b',
    'reims': r'\b(stade\s+de\s+reims|reims|sdr)\b',
    'brest': r'\b(stade\s+brestois|brest|sb29)\b',
    'auxerre': r'\b(aja|auxerre)\b',
    'metz': r'\b(fc\s+metz|metz)\b',
    'angers': r'\b(sco\s+angers|angers)\b',
    'lorient': r'\b(fc\s+lorient|lorient|fcl)\b',
    'le_havre': r'\b(hac|le\s+havre)\b',
    'guingamp': r'\b(eag|guingamp|en\s+avant\s+guingamp)\b',
    'valenciennes': r'\b(vafc|valenciennes)\b',
    'clermont': r'\b(clermont\s+foot|clermont|cf63)\b',
    'caen': r'\b(sm\s+caen|stade\s+malherbe|caen)\b',
    'bastia': r'\b(sc\s+bastia|bastia|sporting\s+bastia)\b',
    'ajaccio': r'\b(ac\s+ajaccio|ajaccio|gfca|gazelec)\b',
    'troyes': r'\b(estac|troyes)\b',
    'sochaux': r'\b(fc\s+sochaux|sochaux|fcsm)\b',
    'grenoble': r'\b(grenoble\s+foot|gf38|grenoble)\b',
    'paris_fc': r'\b(paris\s+fc|pfc)\b',
    'amiens': r'\b(amiens\s+sc|amiens)\b',
    'laval': r'\b(stade\s+lavallois|laval)\b',
    'nimes': r'\b(n[iî]mes\s+olympique|n[iî]mes)\b',
    'nancy': r'\b(as\s+nancy|asnl|nancy\s+lorraine)\b',
    'dijon': r'\b(dfco|dijon\s+fco|dijon)\b',
    'asse': r'\b(asse|saint[- \.]*etienne|st[- \.]*etienne|sainté|saint[- \.]*étienne|st[- \.]*étienne)\b',
    'real_madrid': r'\b(real\s+madrid)\b',
    'barcelona': r'\b(barcelona|bar[çc]a)\b',
    'atletico': r'\b(atletico\s+madrid|atletico)\b',
    'sevilla': r'\b(sevilla|seville)\b',
    'valencia': r'\b(valencia|valence)\b',
    'villarreal': r'\b(villarr?eal)\b',
    'betis': r'\b(betis)\b',
    'bilbao': r'\b(athletic\s+bilbao|bilbao)\b',
    'man_united': r'\b(manchester\s+united|man\s+utd)\b',
    'man_city': r'\b(manchester\s+city|man\s+city)\b',
    'liverpool': r'\b(liverpool)\b',
    'arsenal': r'\b(arsenal)\b',
    'chelsea': r'\b(chelsea)\b',
    'tottenham': r'\b(tottenham|spurs)\b',
    'newcastle': r'\b(newcastle)\b',
    'aston_villa': r'\b(aston\s+villa)\b',
    'everton': r'\b(everton)\b',
    'west_ham': r'\b(west\s+ham)\b',
    'juventus': r'\b(juventus|juve)\b',
    'milan': r'\b(ac\s+milan|milan\s+ac)\b',
    'inter': r'\b(inter\s+milan|inter)\b',
    'napoli': r'\b(napoli|naples)\b',
    'roma': r'\b(as\s+roma|roma)\b',
    'lazio': r'\b(lazio)\b',
    'fiorentina': r'\b(fiorentina)\b',
    'bayern': r'\b(bayern\s+munich|bayern)\b',
    'dortmund': r'\b(borussia\s+dortmund|dortmund)\b',
    'leverkusen': r'\b(bayer\s+leverkusen|leverkusen)\b',
    'leipzig': r'\b(rb\s+leipzig|leipzig)\b',
    'schalke': r'\b(schalke\s*04|schalke)\b',
    'ajax': r'\b(ajax\s+amsterdam|ajax)\b',
    'benfica': r'\b(benfica)\b',
    'porto': r'\b(fc\s+porto|porto)\b',
    'sporting': r'\b(sporting\s+lisbon[ae]?|sporting\s+cp)\b',
    'psv': r'\b(psv\s+eindhoven|psv)\b',
    'feyenoord': r'\b(feyenoord)\b',
    'galatasaray': r'\b(galatasaray)\b',
    'celtic': r'\b(celtic\s+glasgow|celtic)\b',
    'rangers': r'\b(glasgow\s+rangers|rangers)\b'
}

def is_explicit_asse_jersey(title, desc=""):
    """
    Vérifie si l'article est EXPLICITEMENT un article / maillot de l'ASSE :
    1. Soit le titre mentionne directement l'ASSE / Saint-Etienne (hors lot multi-articles).
    2. Soit la description associe explicitement un maillot/vêtement à l'ASSE (ex: 'maillot de l'asse', 'maillot st etienne', 'tenue asse').
    """
    import re
    t = (title or "").lower()
    d = (desc or "").lower()

    # 1. Dans le titre : mention claire de l'ASSE (sauf si annonce de type lot multi-articles)
    if is_asse_jersey_match(t):
        if not re.search(r'\b(lot|lots|plusieurs)\s+(?:de\s+)?(?:maillots|articles|t-?shirts)\b', t):
            return True

    # 2. Dans la description : formulation sans équivoque liant le vêtement à l'ASSE
    explicit_desc_patterns = [
        r'\b(?:maillot|jersey|vareuse|t-?shirt|ensemble|tenue|polo)\s+(?:de\s+(?:l[\'\s])?)?(?:l[\'\s])?(?:asse|saint[- \.]*etienne|st[- \.]*etienne|sainté|saint[- \.]*étienne|st[- \.]*étienne)\b',
        r'\b(?:asse|saint[- \.]*etienne|st[- \.]*etienne|sainté|saint[- \.]*étienne|st[- \.]*étienne)\s+(?:maillot|jersey|vareuse|domicile|ext[ée]rieur|third|vintage|collector|flocage|manufrance|supert[ée]l[ée]|duarig|le\s+coq\s+sportif|puma|adidas|hummel|kappa)\b',
        r'\b(?:vends|vente)\s+(?:un\s+|mon\s+|ce\s+)?(?:maillot|jersey)\s+(?:de\s+(?:l[\'\s])?)?(?:l[\'\s])?(?:asse|saint[- \.]*etienne|st[- \.]*etienne|sainté)\b'
    ]
    for pat in explicit_desc_patterns:
        if re.search(pat, d):
            return True

    return False

# Dictionnaire des équipes et pays concurrents (pour le filtrage liste noire du Filet de sécurité)
OTHER_TEAMS_PATTERNS = {
    # Nations / Sélections nationales
    'France (hors ASSE)': r'\b(equipe\s+de\s+france|edf|france\s*98|france\s*20\d\d|fff)\b',
    'Italie': r'\b(italie|italia|italy)\b',
    'Allemagne': r'\b(allemagne|germany|deutschland)\b',
    'Belgique': r'\b(belgique|belgium|belgie)\b',
    'Espagne': r'\b(espagne|spain|espana)\b',
    'Portugal': r'\b(portugal)\b',
    'Angleterre': r'\b(angleterre|england)\b',
    'Brésil': r'\b(br[eé]sil|brazil|brasil)\b',
    'Argentine': r'\b(argentine|argentina)\b',
    'Pays-Bas': r'\b(pays[- ]bas|netherlands|hollande|holland)\b',
    'Croatie': r'\b(croatie|croatia)\b',
    'Maroc': r'\b(maroc|morocco)\b',
    'Algérie': r'\b(alg[eé]rie|algeria)\b',
    'Tunisie': r'\b(tunisie|tunisia)\b',
    'Sénégal': r'\b(s[eé]n[eé]gal|senegal)\b',
    'Cameroun': r'\b(cameroun|cameroon)\b',
    'Côte d\'Ivoire': r'\b(c[oô]te\s+d[\'\s]ivoire|ivory\s+coast)\b',
    'Ghana': r'\b(ghana|black\s+stars)\b',
    'Gabon': r'\b(gabon|panth[eè]res\s+du\s+gabon)\b',
    'Mali': r'\b(mali|aigles\s+du\s+mali)\b',
    'Guinée': r'\b(guin[eé]e|guinea|syli)\b',
    'RD Congo': r'\b(rdc|rd\s+congo|congo|l[eé]opards)\b',
    'Égypte': r'\b([eé]gypte|egypt)\b',
    'Nigéria': r'\b(nig[eé]ria|nigeria)\b',
    'Japon': r'\b(japon|japan)\b',
    'Corée': r'\b(cor[eé]e|korea)\b',
    'Australie': r'\b(australie|australia)\b',
    'Mexique': r'\b(mexique|mexico)\b',
    'USA': r'\b(usa|etats[- ]unis|[eé]tats[- ]unis|united\s+states)\b',
    'Canada': r'\b(canada)\b',
    'Colombie': r'\b(colombie|colombia)\b',
    'Uruguay': r'\b(uruguay)\b',
    'Chili': r'\b(chili|chile)\b',
    'Pérou': r'\b(p[eé]rou|peru)\b',
    'Suisse': r'\b(suisse|switzerland)\b',
    'Suède': r'\b(su[eè]de|sweden)\b',
    'Danemark': r'\b(danemark|denmark)\b',
    'Norvège': r'\b(norv[eè]ge|norway)\b',
    'Pologne': r'\b(pologne|poland)\b',
    'Autriche': r'\b(autriche|austria)\b',
    'Écosse': r'\b([eé]cosse|scotland)\b',
    'Irlande': r'\b(irlande|ireland)\b',
    'Pays de Galles': r'\b(pays\s+de\s+galles|wales)\b',
    'Grèce': r'\b(gr[eè]ce|greece)\b',
    'Turquie': r'\b(turquie|turkey)\b',
    'Tchéquie': r'\b(r[eé]publique\s+tch[eè]que|tch[eè]quie|czech)\b',
    'Serbie': r'\b(serbie|serbia)\b',
    'Roumanie': r'\b(roumanie|romania)\b',
    'Hongrie': r'\b(hongrie|hungary)\b',
    'Ukraine': r'\b(ukraine)\b',
    'Russie': r'\b(russie|russia)\b',
    
    # Clubs français majeurs
    'PSG': r'\b(psg|paris\s+sg|paris\s+saint[- ]germain)\b',
    'OM': r'\b(om|marseille|olympique\s+de\s+marseille)\b',
    'OL': r'\b(ol|lyon|olympique\s+lyonnais)\b',
    'Lens': r'\b(rc\s+lens|lens|rcl)\b',
    'Lille': r'\b(losc|lille)\b',
    'Monaco': r'\b(as\s+monaco|monaco|asm)\b',
    'Rennes': r'\b(stade\s+rennais|rennes|srfc)\b',
    'Nantes': r'\b(fc\s+nantes|nantes|fcn)\b',
    'Nice': r'\b(ogc\s+nice|nice\s+ogc|ogcn|maillot\s+(?:de\s+)?nice)\b',
    'Bordeaux': r'\b(girondins|bordeaux|fcgb)\b',
    'Montpellier': r'\b(mhsc|mshc|montpellier)\b',
    'Strasbourg': r'\b(rcsa|strasbourg)\b',
    'Toulouse': r'\b(tfc|toulouse)\b',
    'Reims': r'\b(stade\s+de\s+reims|reims|sdr)\b',
    'Brest': r'\b(stade\s+brestois|brest|sb29)\b',
    'Auxerre': r'\b(aja|auxerre)\b',
    'Metz': r'\b(fc\s+metz|metz)\b',
    'Lorient': r'\b(fc\s+lorient|lorient|fcl)\b',
    'Angers': r'\b(sco\s+angers|angers\s+sco|angers)\b',
    'Le Havre': r'\b(hac|le\s+havre)\b',
    'Guingamp': r'\b(eag|guingamp|en\s+avant\s+guingamp)\b',
    'Valenciennes': r'\b(vafc|valenciennes)\b',
    'Clermont': r'\b(clermont\s+foot|clermont|cf63)\b',
    'Caen': r'\b(sm\s+caen|stade\s+malherbe|caen)\b',
    'Bastia': r'\b(sc\s+bastia|bastia|sporting\s+bastia)\b',
    'Ajaccio': r'\b(ac\s+ajaccio|ajaccio|gfca|gazelec)\b',
    'Troyes': r'\b(estac|troyes)\b',
    'Sochaux': r'\b(fc\s+sochaux|sochaux|fcsm)\b',
    'Grenoble': r'\b(grenoble\s+foot|gf38|grenoble)\b',
    'Paris FC': r'\b(paris\s+fc|pfc)\b',
    'Amiens': r'\b(amiens\s+sc|amiens)\b',
    'Laval': r'\b(stade\s+lavallois|laval)\b',
    'Nîmes': r'\b(n[iî]mes\s+olympique|n[iî]mes)\b',
    'Nancy': r'\b(as\s+nancy|asnl|nancy\s+lorraine)\b',
    'Dijon': r'\b(dfco|dijon\s+fco|dijon)\b',
    'Sedan': r'\b(cssa|cs\s+sedan|sedan\s+ardenne|sedan)\b',
    'Châteauroux': r'\b(ch[aâ]teauroux|berrichonne|lb\s+ch[aâ]teauroux)\b',
    'Gueugnon': r'\b(gueugnon|fcgb71)\b',
    'Red Star': r'\b(red\s+star)\b',
    'Le Mans': r'\b(le\s+mans\s+fc|le\s+mans|muc\s*72)\b',
    'Tours': r'\b(tours\s+fc|tours)\b',
    'Boulogne': r'\b(usbco|boulogne[- ]sur[- ]mer)\b',
    'Niort': r'\b(chamois\s+niortais|niort)\b',
    'Rodez': r'\b(rodez\s+af|raf|rodez)\b',
    'Pau': r'\b(pau\s+fc|pau)\b',
    'Dunkerque': r'\b(usl\s+dunkerque|dunkerque)\b',
    'Annecy': r'\b(fc\s+annecy|annecy)\b',
    'Quevilly': r'\b(qrm|quevilly)\b',
    'Orléans': r'\b(us\s+orl[eé]ans|orl[eé]ans)\b',
    'Martigues': r'\b(fc\s+martigues|martigues)\b',
    'Istres': r'\b(fc\s+istres|istres)\b',
    'Cannes': r'\b(as\s+cannes|cannes)\b',
    'Rouen': r'\b(fc\s+rouen|rouen)\b',

    # Clubs européens
    'Freiburg': r'\b(sc\s+freiburg|freiburg|fribourg)\b',
    'Eintracht Francfort': r'\b(eintracht\s+frankfurt|frankfurt|francfort)\b',
    'RB Leipzig': r'\b(rb\s+leipzig|leipzig|rbl)\b',
    'Union Berlin': r'\b(union\s+berlin)\b',
    'Hertha Berlin': r'\b(hertha\s+berlin|hertha|bsc)\b',
    'Augsburg': r'\b(fc\s+augsburg|augsburg)\b',
    'Mainz': r'\b(fsv\s+mainz|mainz|mayence)\b',
    'Hoffenheim': r'\b(tsg\s+hoffenheim|hoffenheim)\b',
    'Bochum': r'\b(vfl\s+bochum|bochum)\b',
    'Heidenheim': r'\b(fc\s+heidenheim|heidenheim)\b',
    'St. Pauli': r'\b(st[\.\s]*pauli|saint[\-\s]pauli)\b',
    'Hambourg': r'\b(hamburger\s+sv|hsv|hambourg|hamburg)\b',
    'Düsseldorf': r'\b(fortuna\s+d[uü]sseldorf|d[uü]sseldorf)\b',
    'Hanovre': r'\b(hannover\s+96|hannover|hanovre)\b',
    'Nuremberg': r'\b(fc\s+n[uü]rnberg|nuremberg|n[uü]rnberg)\b',
    'Kaiserslautern': r'\b(kaiserslautern|fck)\b',
    'Karlsruhe': r'\b(karlsruher\s+sc|ksc|karlsruhe)\b',
    'Sant Andreu': r'\b(sant\s+andreu|ue\s+sant\s+andreu)\b',
    'Real Madrid': r'\b(real\s+madrid)\b',
    'FC Barcelone': r'\b(barcelona|bar[çc]a)\b',
    'Atletico': r'\b(atletico\s+madrid|atletico)\b',
    'Juventus': r'\b(juventus|juve)\b',
    'AC Milan': r'\b(ac\s+milan|milan\s+ac)\b',
    'Inter Milan': r'\b(inter\s+milan)\b',
    'Bayern Munich': r'\b(bayern\s+munich|bayern)\b',
    'Dortmund': r'\b(borussia\s+dortmund|dortmund)\b',
    'Liverpool': r'\b(liverpool)\b',
    'Arsenal': r'\b(arsenal)\b',
    'Chelsea': r'\b(chelsea)\b',
    'Manchester United': r'\b(manchester\s+united|man\s+utd)\b',
    'Manchester City': r'\b(manchester\s+city|man\s+city)\b',
    'Manchester': r'\b(manchester)\b',
    'Tottenham': r'\b(tottenham|spurs)\b',
    'Crystal Palace': r'\b(crystal\s+palace)\b',
    'Fulham': r'\b(fulham)\b',
    'Wolverhampton': r'\b(wolverhampton|wolves)\b',
    'Brentford': r'\b(brentford)\b',
    'Brighton': r'\b(brighton|brighton\s+&\s+hove)\b',
    'Bournemouth': r'\b(bournemouth|afc\s+bournemouth)\b',
    'Everton': r'\b(everton)\b',
    'West Ham': r'\b(west\s+ham)\b',
    'Aston Villa': r'\b(aston\s+villa)\b',
    'Newcastle': r'\b(newcastle|newcastle\s+united)\b',
    'Southampton': r'\b(southampton)\b',
    'Leicester': r'\b(leicester|leicester\s+city)\b',
    'Ipswich': r'\b(ipswich|ipswich\s+town)\b',
    'Nottingham Forest': r'\b(nottingham|nottingham\s+forest)\b',
    'Leeds': r'\b(leeds|leeds\s+united)\b',
    'Sunderland': r'\b(sunderland|sunderland\s+afc)\b',
    'Swansea': r'\b(swansea|swansea\s+city)\b',
    'Watford': r'\b(watford|watford\s+fc)\b',
    'Stoke City': r'\b(stoke\s+city)\b',
    'West Bromwich': r'\b(west\s+bromwich|wba)\b',
    'Middlesbrough': r'\b(middlesbrough)\b',
    'Burnley': r'\b(burnley)\b',
    'Sheffield': r'\b(sheffield)\b',
    'Ajax': r'\b(ajax\s+amsterdam|ajax)\b',
    'PSV Eindhoven': r'\b(psv|psv\s+eindhoven)\b',
    'Feyenoord': r'\b(feyenoord)\b',
    'Porto': r'\b(fc\s+porto)\b',
    'Benfica': r'\b(benfica|sl\s+benfica)\b',
    'Braga': r'\b(sc\s+braga)\b',
    'AS Roma': r'\b(as\s+roma|roma)\b',
    'Lazio': r'\b(lazio|ss\s+lazio)\b',
    'Naples': r'\b(napoli|ssc\s+napoli|naples)\b',
    'Fiorentina': r'\b(fiorentina)\b',
    'Atalanta': r'\b(atalanta)\b',
    'Torino': r'\b(torino)\b',
    'Sampdoria': r'\b(sampdoria)\b',
    'Udinese': r'\b(udinese)\b',
    'Parme': r'\b(parma|parme)\b',
    'Valence': r'\b(valencia\s+cf|valence\s+cf)\b',
    'Séville': r'\b(sevilla\s+fc|fc\s+s[eé]ville)\b',
    'Villarreal': r'\b(villarreal)\b',
    'Real Sociedad': r'\b(real\s+sociedad)\b',
    'Athletic Bilbao': r'\b(athletic\s+bilbao|athletic\s+club)\b',
    'Leverkusen': r'\b(bayer\s+leverkusen|leverkusen)\b',
    'Schalke': r'\b(schalke)\b',
    'Stuttgart': r'\b(vfb\s+stuttgart|stuttgart)\b',
    'Francfort': r'\b(eintracht\s+frankfurt|eintracht\s+francfort)\b',
    'Cologne': r'\b(fc\s+k[oö]ln|fc\s+cologne)\b',
    'Mönchengladbach': r'\b(m[oö]nchengladbach|gladbach)\b',
    'Galatasaray': r'\b(galatasaray)\b',
    'Fenerbahçe': r'\b(fenerbah[cç]e)\b',
    'Besiktas': r'\b(besiktas|be[sş]ikta[sş])\b',
    'Trabzonspor': r'\b(trabzonspor)\b',
    'Dynamo Kiev': r'\b(dynamo\s+kiev|dynamo\s+kyiv)\b',
    'Shakhtar': r'\b(shakhtar)\b',
    'Olympiakos': r'\b(olympiakos|olympiacos)\b',
    'PAOK': r'\b(paok)\b',
    'Anderlecht': r'\b(anderlecht|rsca)\b',
    'Standard Liège': r'\b(standard\s+de\s+li[eè]ge|standard\s+li[eè]ge)\b',
    'Club Bruges': r'\b(club\s+bruges|club\s+brugge)\b',

    # Clubs et sélections jouant en vert ou fréquents en faux positifs
    'Celtic Glasgow': r'\b(celtic|celtic\s+glasgow|glasgow\s+celtic)\b',
    'Real Betis': r'\b(betis|real\s+betis|betis\s+s[eé]ville|betis\s+balompi[eé])\b',
    'Werder Brême': r'\b(werder|werder\s+br[eê]me|werder\s+bremen)\b',
    'Wolfsburg': r'\b(wolfsburg|vfl\s+wolfsburg)\b',
    'Panathinaikos': r'\b(panathinaikos|pana)\b',
    'Sporting CP': r'\b(sporting\s+cp|sporting\s+portugal|sporting\s+lisbonne|sporting\s+clube|sporting\s+lisboa)\b',
    'Palmeiras': r'\b(palmeiras|verd[aã]o)\b',
    'Sassuolo': r'\b(sassuolo|us\s+sassuolo)\b',
    'Rapid Vienne': r'\b(rapid\s+vienne|rapid\s+wien)\b',
    'Legia Varsovie': r'\b(legia|legia\s+varsovie|legia\s+warszawa)\b',
    'Plymouth': r'\b(plymouth|plymouth\s+argyle)\b',
    'Hibernian': r'\b(hibernian|hibs)\b',
    'Seattle Sounders': r'\b(sounders|seattle\s+sounders)\b',
    'Austin FC': r'\b(austin\s+fc)\b',
    'Portland Timbers': r'\b(portland\s+timbers|timbers)\b',
    'Darmstadt': r'\b(darmstadt|sv\s+darmstadt)\b',
    'Greuther Fürth': r'\b(greuther\s+f[uü]rth|f[uü]rth)\b',
    'Saint-Gall': r'\b(st[\.\s]*gallen|saint[\-\s]gall|fc\s+st[\.\s]*gallen)\b',
    'Saint-Patrick\'s': r'\b(st\s+patrick|st\s+patricks|saint\s+patrick)\b',
    'Shamrock Rovers': r'\b(shamrock|shamrock\s+rovers)\b',
    'Wydad': r'\b(wydad|wac)\b',
    'Raja Casablanca': r'\b(raja|raja\s+casablanca|rca)\b',
    'MC Alger': r'\b(mc\s+alger|mca)\b',
    'JS Kabylie': r'\b(js\s+kabylie|jsk)\b',
    'Chapecoense': r'\b(chapecoense)\b',
    'Coritiba': r'\b(coritiba)\b',
    'Goiás': r'\b(goi[aá]s)\b',
    'Ferencváros': r'\b(ferencv[aá]ros|fradi)\b',
    'La Louvière': r'\b(la\s+louvi[eè]re|raal)\b',
    'Ludogorets': r'\b(ludogorets)\b',
    'Bohemians Prague': r'\b(bohemians\s+1905|bohemians\s+prague)\b',
    'Avellino': r'\b(us\s+avellino|avellino)\b',
    'Elche': r'\b(elche\s+cf|elche)\b',
    'Racing Santander': r'\b(racing\s+santander|santander)\b',
    'Córdoba': r'\b(c[oó]rdoba\s+cf)\b',
    'Rio Ave': r'\b(rio\s+ave)\b',
    'Moreirense': r'\b(moreirense)\b',
    'Omonia Nicosie': r'\b(omonia|omonia\s+nicosie)\b',
    'Lechia Gdansk': r'\b(lechia\s+gdansk|lechia)\b',
    'Slask Wroclaw': r'\b([sś]l[aą]sk\s+wroc[lł]aw)\b',
    'Forest Green': r'\b(forest\s+green)\b',
    'Atletico Nacional': r'\b(atl[eé]tico\s+nacional|atletico\s+nacional)\b',
    'Deportivo Cali': r'\b(deportivo\s+cali)\b',
    'Club León': r'\b(club\s+le[oó]n|le[oó]n\s+fc)\b',
    'Santos Laguna': r'\b(santos\s+laguna)\b',
    'Al Ahli': r'\b(al[\-\s]?ahli)\b',
    'Al Ettifaq': r'\b(al[\-\s]?ettifaq)\b',
    'Arabie Saoudite': r'\b(arabie\s+saoudite|saudi\s+arabia|saudi)\b',
    'Bolivie': r'\b(bolivie|bolivia)\b',
    'Zambie': r'\b(zambie|zambia)\b',
    'Afrique du Sud': r'\b(afrique\s+du\s+sud|south\s+africa|bafana\s+bafana|springboks)\b',
    'Malte': r'\b(malte|malta)\b',

    # Sélections nationales (Europe, Afrique, Amériques, Asie)
    'Islande': r'\b(islande|iceland)\b',
    'Slovaquie': r'\b(slovaquie|slovakia)\b',
    'Slovénie': r'\b(slov[eé]nie|slovenia)\b',
    'Albanie': r'\b(albanie|albania)\b',
    'Bosnie': r'\b(bosnie|bosnia)\b',
    'Macédoine': r'\b(mac[eé]doine|macedonia)\b',
    'Finlande': r'\b(finlande|finland)\b',
    'Luxembourg': r'\b(luxembourg)\b',
    'Géorgie': r'\b(g[eé]orgie|georgia)\b',
    'Israël': r'\b(isra[eë]l)\b',
    'Burkina Faso': r'\b(burkina\s+faso|burkina|[eé]talons\s+du\s+burkina)\b',
    'Togo': r'\b(togo|[eé]perviers\s+du\s+togo)\b',
    'Bénin': r'\b(b[eé]nin|gu[eé]pards\s+du\s+b[eé]nin)\b',
    'Angola': r'\b(angola|palancas\s+negras)\b',
    'Mauritanie': r'\b(mauritanie|mourabitounes)\b',
    'Cap-Vert': r'\b(cap[\-\s]vert|cabo\s+verde|tubar[oõ]es\s+azuis)\b',
    'Comores': r'\b(comores|coelacanthes)\b',
    'Gambie': r'\b(gambie|gambia|scorpions\s+de\s+gambie)\b',
    'Guinée Équatoriale': r'\b(guin[eé]e\s+[eé]quatoriale|nzalang\s+nacional)\b',
    'Guinée-Bissau': r'\b(guin[eé]e[\-\s]bissau|djurtus)\b',
    'Madagascar': r'\b(madagascar|barea)\b',
    'Mozambique': r'\b(mozambique|mambas)\b',
    'Namibie': r'\b(namibie|namibia|brave\s+warriors)\b',
    'Soudan': r'\b(soudan|sudan)\b',
    'Tanzanie': r'\b(tanzanie|tanzania|taifa\s+stars)\b',
    'Ouganda': r'\b(ouganda|uganda|cranes)\b',
    'Zimbabwe': r'\b(zimbabwe|warriors)\b',
    'Paraguay': r'\b(paraguay|albirroja)\b',
    'Équateur': r'\b([eé]quateur|ecuador|la\s+tri)\b',
    'Venezuela': r'\b(venezuela|vinotinto)\b',
    'Costa Rica': r'\b(costa\s+rica|los\s+ticos)\b',
    'Panama': r'\b(panama|los\s+canaleros)\b',
    'Jamaïque': r'\b(jama[iï]que|jamaica|reggae\s+boyz)\b',
    'Honduras': r'\b(honduras|los\s+catrachos)\b',
    'Haïti': r'\b(ha[iï]ti|grenadiers)\b',
    'Iran': r'\b(iran|team\s+melli)\b',
    'Irak': r'\b(irak|iraq)\b',
    'Qatar': r'\b(qatar|al[\-\s]?annabi)\b',
    'Émirats': r'\b([eé]mirats|emirates|eau|uae)\b',
    'Chine': r'\b(chine|china)\b',
    'Ouzbékistan': r'\b(ouzb[eé]kistan|uzbekistan)\b',
    'Nouvelle-Zélande': r'\b(nouvelle[\-\s]z[eé]lande|new\s+zealand|all\s+whites)\b',

    # Clubs majeurs européens (Liga, Serie A, Bundesliga, Championship, C1/C3)
    'Girona': r'\b(girona\s+fc|girona|g[eé]rone)\b',
    'Celta Vigo': r'\b(celta\s+vigo|celta)\b',
    'Espanyol Barcelone': r'\b(espanyol|rcd\s+espanyol)\b',
    'Osasuna': r'\b(osasuna|ca\s+osasuna)\b',
    'Mallorca': r'\b(rcd\s+mallorca|mallorca|majorque)\b',
    'Rayo Vallecano': r'\b(rayo\s+vallecano|rayo)\b',
    'Getafe': r'\b(getafe\s+cf|getafe)\b',
    'Alavés': r'\b(alav[eé]s|deportivo\s+alav[eé]s)\b',
    'Las Palmas': r'\b(ud\s+las\s+palmas|las\s+palmas)\b',
    'Valladolid': r'\b(real\s+valladolid|valladolid)\b',
    'Cadix': r'\b(c[aá]diz\s+cf|c[aá]diz|cadix)\b',
    'Grenade': r'\b(granada\s+cf|granada)\b',
    'Deportivo La Corogne': r'\b(deportivo\s+la\s+coru[nñ]a|depor|la\s+corogne)\b',
    'Saragosse': r'\b(real\s+zaragoza|zaragoza|saragosse)\b',
    'Bologne': r'\b(bologna\s+fc|bologna|bologne)\b',
    'Genoa': r'\b(genoa|cfc\s+genoa)\b',
    'Hellas Vérone': r'\b(hellas\s+verona|hellas|v[eé]rone)\b',
    'Cagliari': r'\b(cagliari\s+calcio|cagliari)\b',
    'Lecce': r'\b(us\s+lecce|lecce)\b',
    'Monza': r'\b(ac\s+monza|monza)\b',
    'Côme': r'\b(como\s+1907|c[oô]me)\b',
    'Empoli': r'\b(empoli\s+fc|empoli)\b',
    'Venise': r'\b(venezia\s+fc|venise|venezia)\b',
    'Salernitana': r'\b(salernitana)\b',
    'Palerme': r'\b(palermo\s+fc|palermo|palerme)\b',
    'Bari': r'\b(ssc\s+bari|bari)\b',
    'Holstein Kiel': r'\b(holstein\s+kiel|kiel)\b',
    'Paderborn': r'\b(sc\s+paderborn|paderborn)\b',
    'Arminia Bielefeld': r'\b(arminia\s+bielefeld|bielefeld)\b',
    'Hansa Rostock': r'\b(hansa\s+rostock|rostock)\b',
    'Magdebourg': r'\b(1\.\s*fc\s+magdeburg|magdeburg|magdebourg)\b',
    'Norwich': r'\b(norwich|norwich\s+city)\b',
    'Blackburn': r'\b(blackburn|blackburn\s+rovers)\b',
    'Cardiff': r'\b(cardiff|cardiff\s+city)\b',
    'Portsmouth': r'\b(portsmouth|pompey)\b',
    'QPR': r'\b(qpr|queens\s+park\s+rangers)\b',
    'Luton': r'\b(luton|luton\s+town)\b',
    'Millwall': r'\b(millwall)\b',
    'Derby County': r'\b(derby\s+county)\b',
    'Coventry': r'\b(coventry|coventry\s+city)\b',
    'Preston': r'\b(preston\s+north\s+end)\b',
    'Hull City': r'\b(hull\s+city)\b',
    'Bristol City': r'\b(bristol\s+city)\b',
    'Glasgow Rangers': r'\b(glasgow\s+rangers|rangers\s+fc|rangers)\b',
    'Aberdeen': r'\b(aberdeen\s+fc|aberdeen)\b',
    'Hearts': r'\b(hearts|heart\s+of\s+midlothian)\b',
    'Young Boys Berne': r'\b(young\s+boys|yb\s+bern|bsc\s+young\s+boys)\b',
    'FC Bâle': r'\b(fc\s+b[aâ]le|fc\s+basel|basel)\b',
    'FC Zurich': r'\b(fc\s+z[uü]rich|z[uü]rich)\b',
    'Servette Genève': r'\b(servette\s+fc|servette\s+gen[eè]ve|servette)\b',
    'Red Bull Salzbourg': r'\b(rb\s+salzburg|salzburg|salzbourg)\b',
    'Sturm Graz': r'\b(sturm\s+graz|graz)\b',
    'Austria Vienne': r'\b(austria\s+wien|austria\s+vienne)\b',
    'Union Saint-Gilloise': r'\b(union\s+saint[\-\s]gilloise|usg)\b',
    'KRC Genk': r'\b(krc\s+genk|racing\s+genk|genk)\b',
    'La Gantoise': r'\b(la\s+gantoise|kaa\s+gent|gent)\b',
    'Royal Antwerp': r'\b(royal\s+antwerp|antwerp|anvers)\b',
    'Charleroi': r'\b(sporting\s+charleroi|charleroi)\b',
    'Cercle Bruges': r'\b(cercle\s+brugge|cercle\s+bruges)\b',
    'AZ Alkmaar': r'\b(az\s+alkmaar|alkmaar)\b',
    'FC Twente': r'\b(fc\s+twente|twente)\b',
    'FC Utrecht': r'\b(fc\s+utrecht|utrecht)\b',
    'Vitesse Arnhem': r'\b(vitesse\s+arnhem|vitesse)\b',
    'Guimarães': r'\b(vit[oó]ria\s+guimar[aã]es|guimar[aã]es)\b',
    'Boavista': r'\b(boavista)\b',
    'Slavia Prague': r'\b(slavia\s+prague|slavia\s+praha|slavia)\b',
    'Sparta Prague': r'\b(sparta\s+prague|sparta\s+praha|sparta)\b',
    'Viktoria Plzen': r'\b(viktoria\s+plze[nň]|plzen)\b',
    'Dinamo Zagreb': r'\b(dinamo\s+zagreb)\b',
    'Hajduk Split': r'\b(hajduk\s+split|hajduk)\b',
    'Rijeka': r'\b(hnk\s+rijeka|rijeka)\b',
    'Etoile Rouge': r'\b([eé]toile\s+rouge|crvena\s+zvezda|red\s+star\s+belgrade)\b',
    'Partizan Belgrade': r'\b(partizan\s+belgrade|partizan)\b',
    'FC Copenhague': r'\b(fc\s+copenhague|copenhague|fc\s+k[oø]benhavn|k[oø]benhavn)\b',
    'Brøndby': r'\b(br[oø]ndby|bif)\b',
    'Midtjylland': r'\b(fc\s+midtjylland|midtjylland)\b',
    'Bodo Glimt': r'\b(bod[oø][\s\-]glimt|glimt)\b',
    'Rosenborg': r'\b(rosenborg|rbk)\b',
    'Molde': r'\b(molde\s+fk|molde)\b',
    'Malmö': r'\b(malm[oö]\s+ff|malm[oö])\b',
    'AIK Stockholm': r'\b(aik\s+stockholm|aik)\b',
    'Djurgården': r'\b(djurg[aå]rden|dif)\b',
    'Maccabi Tel Aviv': r'\b(maccabi\s+tel[\-\s]?aviv)\b',
    'Maccabi Haïfa': r'\b(maccabi\s+ha[iï]fa)\b',
    'Qarabag': r'\b(qarabag|karabakh)\b',
    'Basaksehir': r'\b(basaksehir|ba[sş]ak[sş]ehir)\b'
}

def is_conflicting_team(text):
    """
    Détecte si le texte concerne explicitement une autre équipe ou nation concurrente,
    en ignorant les mentions d'adversaires (ex: 'contre Montpellier', 'vs OM', 'face à Lyon', 'porté de asse marseille').
    """
    if not text:
        return False, None
    import re, unicodedata
    t = text.lower()
    t_norm = ''.join(c for c in unicodedata.normalize('NFD', t) if unicodedata.category(c) != 'Mn').replace('’', "'")
    
    # 1. Neutraliser les mentions d'adversaires et confrontations (ex: 'contre OM', 'vs Lyon', 'match contre Marseille', 'porté contre ASSE')
    opponent_pattern = r'\b(?:(?:port[eé](?:\s+(?:un\s+)?match)?\s+|match\s+|jou[eé]\s+)?(?:contre|vs\.?|face\s+[àa]|oppos[eé][es]?\s+[àa]))\s+([a-z0-9\-\'\s]+?)(?=\s+(?:en|le|du|au|pour|saison|19\d\d|20\d\d|de\s+[a-z]+)\b|[,\.;\(\)\!]|$)'
    t_clean = re.sub(opponent_pattern, ' ', t_norm)
    
    # 2. Neutraliser les duels directs (ex: 'ASSE - OM', 'ASSE / Marseille', 'Sainté - Lyon')
    confrontation_pattern = r'\b(?:asse|saint[- \.]*etienne|st[- \.]*etienne|sainte)\s*[\-\/]\s*([a-z0-9\-\'\s]+)'
    t_clean = re.sub(confrontation_pattern, ' ', t_clean)

    # 3. Vérifier la présence d'un signal ASSE autonome (qui n'est PAS uniquement la mention de l'adversaire affronté)
    asse_opponent_pattern = r'\b(?:contre|vs\.?|face\s+[àa]|oppos[eé][es]?\s+[àa]|match\s+contre|jou[eé]\s+contre|match\s+face\s+[àa])\s+(?:l[\'\s]*)?(?:equipe\s+de\s+)?(?:as\s+)?(?:saint[- \.]*etienne|asse|st[- \.]*etienne|sainte|verts?)\b'
    t_no_asse_opp = re.sub(asse_opponent_pattern, ' ', t_norm)
    has_standalone_asse = bool(re.search(r'\b(asse|saint[- \.]*etienne|st[- \.]*etienne|sainte)\b|(?:\b|^)a[\.\s\-]+s[\.\s\-]+s[\.\s\-]*e(?:\.|\b)', t_no_asse_opp))
    has_match_context = bool(re.search(r'\b(port[eé]|match|finale|derby|demi[- ]finale|coupe|championnat)\b', t_norm))

    for team_name, pat in OTHER_TEAMS_PATTERNS.items():
        if re.search(pat, t_clean):
            # Si le texte contient l'ASSE hors adversaire et un contexte de match/porté, l'autre club est l'adversaire de la rencontre
            if has_standalone_asse and has_match_context:
                continue
            return True, team_name
    return False, None

# Dictionnaire des groupes de supporters adverses (pour bloquer le tag stuffing et écharpes concurrentes)
RIVAL_SUPPORTER_GROUPS = {
    'bad_gones_lyon': r'\b(bad\s+gones|bg\s*87|bg87|kop\s+virage\s+nord|lyon\s*1950)\b',
    'om_supporters': r'\b(commando\s+ultras|cu\s*84|cu84|south\s+winners|sw\s*87|sw87|marseille\s+trop\s+puissant|mtp|fanatics\s*(?:88|1988|marseille|om)|ultras\s+fanatics|dodgers)\b',
    'psg_supporters': r'\b(supras\s+auteuil|sa\s*91|sa91|boulogne\s+boys|bb\s*85|bb85|collectif\s+ultras\s+paris|c\.u\.p|cup\s+(?:paris|psg|auteuil)|karsud|nautaxia|microbes\s+paris|virage\s+auteuil|tribune\s+boulogne)\b',
    'ultramarines_bordeaux': r'\b(ultramarines|ub\s*87|ub87|devils\s*bordeaux)\b',
    'dve_lille': r'\b(dogues?\s+virage\s+est|dve\s*89|dve89)\b',
    'brigade_loire_nantes': r'\b(brigade\s+loire|bl\s*99|bl99)\b',
    'red_tigers_lens': r'\b(red\s+tigers|rt\s*94|rt94|kop\s+sang\s+et\s+or|bollaert\s+boys|galiboys)\b',
    'butte_paillade_montpellier': r'\b(butte\s+paillade|bp\s*91|bp91|armata\s+ultra)\b',
    'roazhon_celtic_kop_rennes': r'\b(roazhon\s+celtic\s+kop|rck\s*91|rck91)\b',
    'horda_frenetik_metz': r'\b(horda\s+frenetik|hf\s*97|hf97|generation\s+grenat|gg\s*95|gg95)\b',
    'brigade_sud_nice': r'\b(brigade\s+sud\s+nice|bsn\s*85|bsn85|populaire\s+sud)\b',
    'valenciennes_ultras': r'\b(ultras\s+valenciennes|ultras\s+vafc|scheldt\s+fans|roisters)\b',
    'lingons_dijon': r'\b(lingons\s+boys)\b',
    'mnk_caen': r'\b(malherbe\s+normandy\s+kop|mnk\s*96|mnk96)\b',
    'indians_tolosa': r'\b(indians\s+tolosa|it\s*93|it93)\b',
    'strasbourg_ultras': r'\b(ultra\s+boys\s*90|ub\s*90|ub90|kop\s+ciel\s+et\s+blanc)\b',
    'bastia_supporters': r'\b(bastia\s*1905|testa\s+mora)\b',
    'ajaccio_supporters': r'\b(orisonti\s+aiaccini)\b',
    'auxerre_supporters': r'\b(ultras\s+auxerre|ua\s*90|ua90)\b',
    'le_havre_supporters': r'\b(barbarians\s+havrais|bh\s*93|bh93)\b',
    'nancy_supporters': r'\b(snipers\s+nancy|saturday\s+fc)\b',
    'sochaux_supporters': r'\b(tribune\s+nord\s+sochaux|tns\s*03)\b',
    'nimes_supporters': r'\b(gladiators\s+nimes|gn\s*91|gn91)\b',
}

def is_conflicting_supporter_group(text):
    """Détecte les groupes de supporters adverses (Bad Gones, Supras, CU84, UB87, etc.)"""
    if not text:
        return False, None
    import unicodedata
    t_norm = ''.join(c for c in unicodedata.normalize('NFD', str(text).lower()) if unicodedata.category(c) != 'Mn')
    t_norm = t_norm.replace('’', "'")
    for group_name, pat in RIVAL_SUPPORTER_GROUPS.items():
        if re.search(pat, t_norm):
            return True, group_name
    return False, None

def load_asse_knowledge():
    """Charge les bases de connaissances exhaustives des joueurs et sponsors ASSE"""
    import unicodedata
    base_dir = os.path.dirname(os.path.abspath(__file__))
    players_path = os.path.join(base_dir, "asse_players_since_1980.json")
    sponsors_path = os.path.join(base_dir, "asse_sponsors_equipementiers.json")

    # Generic global stars with big careers elsewhere or ambiguous common dictionary words / first names
    generic_stars = {
        'alex', 'aloisio', 'henrique', 'silva', 'bernard', 'david', 'blanc', 'perez', 'pedro',
        'mendy', 'camara', 'traore', 'sissoko', 'cisse', 'bamba', 'fall', 'diallo', 'kante',
        'diarra', 'fofana', 'saliba', 'aubameyang', 'platini', 'matuidi', 'payet', 'veretout',
        'cabaye', 'rocheteau', 'sagnol', 'dabo', 'corgnet', 'samba', 'roger', 'morais', 'moreau',
        'garcia', 'martin', 'nelson', 'andre', 'lucas', 'florentin', 'jorge', 'basto', 'gilles',
        'muller', 'geiger', 'leclerc', 'clement', 'marchal', 'pajot', 'roux', 'bell', 'albert',
        'cruz', 'junior', 'pinto', 'santos', 'costa', 'ferreira', 'gomez', 'lopez',
        'heinz', 'nielsen', 'robert', 'thomas', 'daniel', 'francois', 'schneider',
        'lacroix',
        # Mots courants FR/EN pouvant apparaître sur un t-shirt générique (exigent prénom + nom)
        'green', 'four', 'gros', 'plante', 'mouton', 'bouquet', 'carrot', 'marin', 'sable',
        'moulin', 'medaillon', 'cardinal', 'reis', 'elie', 'simo', 'cuca', 'dobo', 'grax', 'haon',
        'courault', 'cros', 'crom', 'faye', 'fomba', 'guel', 'ilan', 'jamali', 'lamba', 'lambert',
        'lamon', 'llacer', 'macon', 'mahut', 'masudi', 'mege', 'mignot', 'millot', 'morice',
        'nade', 'nery', 'nordin', 'ntep', 'othman', 'pagal', 'panos', 'pardo', 'passi', 'paulao',
        'petrot', 'piatti', 'pignol', 'plante', 'ponsard', 'pontal', 'pouget', 'priou', 'quaye',
        'ravet', 'redon', 'riou', 'rocco', 'saadi', 'saban', 'sacko', 'sagna', 'saivet', 'sako',
        'sall', 'sanogo', 'santana', 'santini', 'sauget', 'sechet', 'soderlund', 'solignac',
        'souici', 'tallec', 'tardieu', 'thioub', 'tormin', 'trauco', 'vada', 'vagner', 'vasseur',
        'viviani', 'wolff', 'yahia', 'youssouf', 'pantaloni',
        # Homonymes internationaux / stars d'autres clubs (exigent prénom + nom si "ASSE" absent)
        'fournier', 'andreu', 'pogba', 'hernandez', 'alonso', 'sanchez', 'jorginho', 'fernandes', 'fernandez',
        'christensen', 'oliveira', 'ramirez', 'rivera', 'laudrup', 'milla', 'almeida', 'guarin',
        'coulibaly', 'kamara', 'ndiaye', 'gueye', 'sarr', 'sakho', 'sidibe', 'bakayoko',
        'thiaw', 'maupay', 'saintmaximin', 'modeste', 'mirallas', 'coupet', 'malbranque',
        'clerc', 'ferri', 'bodmer', 'pavlovic', 'dimitrov', 'machado', 'nilsson', 'esposito', 'diomande'
    }

    full_name_players = {
        'ismael diomande': 'Ismaël Diomandé',
        'marek heinz': 'Marek Heinz',
        'benny nielsen': 'Benny Nielsen',
        'christophe robert': 'Christophe Robert',
        'jean-pierre francois': 'Jean-Pierre François',
        'jean-christophe thomas': 'Jean-Christophe Thomas',
        'jean-francois daniel': 'Jean-François Daniel',
        'leo lacroix': 'Léo Lacroix',
        'etienne green': 'Etienne Green',
        'julien sable': 'Julien Sablé',
        'nicolas marin': 'Nicolas Marin',
        'yoann andreu': 'Yoann Andreu',
        'florentin pogba': 'Florentin Pogba',
        'dominique rocheteau': 'Dominique Rocheteau',
        'michel platini': 'Michel Platini',
        'laurent blanc': 'Laurent Blanc',
        'dimitri payet': 'Dimitri Payet',
        'blaise matuidi': 'Blaise Matuidi',
        'william saliba': 'William Saliba',
        'pierre-emerick aubameyang': 'Pierre-Emerick Aubameyang',
        'jean-michel larque': 'Jean-Michel Larqué',
        'herve revelli': 'Hervé Revelli',
        'patrick revelli': 'Patrick Revelli',
        'osvaldo piazza': 'Osvaldo Piazza',
        'johnny rep': 'Johnny Rep',
        'dominique bathenay': 'Dominique Bathenay',
        'christian lopez': 'Christian Lopez',
        'jacques santini': 'Jacques Santini',
        'gerard farison': 'Gérard Farison',
        'alain merchadier': 'Alain Merchadier',
        'christian sarramagna': 'Christian Sarramagna',
        'georges bereta': 'Georges Bereta',
        'robert herbin': 'Robert Herbin',
        'salif keita': 'Salif Keita',
        'olivier pantaloni': 'Olivier Pantaloni',
        'rachid mekhloufi': 'Rachid Mekhloufi'
    }

    player_names = {}
    if os.path.exists(players_path):
        try:
            with open(players_path, 'r', encoding='utf-8') as f:
                p_data = json.load(f)
            for p in p_data:
                full_name = p.get('nom', '').strip()
                if not full_name:
                    continue
                full_clean = ''.join(c for c in unicodedata.normalize('NFD', full_name) if unicodedata.category(c) != 'Mn').lower()
                full_clean = re.sub(r'[^a-z\s\-]', '', full_clean).strip()
                if len(full_clean.split()) >= 2:
                    full_name_players[full_clean] = full_name
                    full_name_players[full_clean.replace('-', ' ')] = full_name
                parts = full_name.split()
                if parts:
                    last = parts[-1]
                    last_clean = ''.join(c for c in unicodedata.normalize('NFD', last) if unicodedata.category(c) != 'Mn').lower()
                    last_clean = re.sub(r'[^a-z]', '', last_clean)
                    if len(last_clean) >= 4 and last_clean not in generic_stars:
                        player_names[last_clean] = full_name
        except Exception as e:
            log(f"⚠️ Erreur chargement joueurs ASSE: {e}")

    # Joueurs emblématiques ASSE garantis (incluant légendes 1976 + cadres modernes)
    famous_asse = [
        'khazri', 'bouanga', 'ruffier', 'perrin', 'janot', 'beric', 'hamouma', 'aouchiche',
        'krasso', 'davitashvili', 'stassin', 'cafaro', 'bouchouari', 'moueffek', 'amougou',
        'larsonneur', 'maubleu', 'feindouno', 'moravcik', 'brandao', 'gomis', 'gradel',
        'tannane', 'selnaes', 'lemoine', 'cohade', 'guilavogui', 'zouma', 'ghoulam',
        'subotic', 'debuchy', 'cabella', 'diony', 'riviere', 'piquionne',
        'hellebuyck', 'potillon', 'castaneda', 'curkovic', 'janvion', 'zanon', 'roussey',
        'paganelli', 'repellini', 'diakhate', 'larque', 'revelli', 'piazza', 'bathenay',
        'synaeghel', 'merchadier', 'sarramagna', 'zimako', 'larios', 'bereta', 'herbin',
        'mekhloufi', 'bergessio', 'bocanegra', 'matsui', 'batlles', 'alonzo', 'tavlaridis'
    ]
    for fn in famous_asse:
        if fn not in player_names:
            player_names[fn] = fn.capitalize()

    # Sponsors & équipementiers exclusifs ASSE
    distinctive_sponsors = [
        'manufrance', 'super tele', 'supertele', 'super télé', 'kb jardin', 'kb-jardin',
        'cake rocher', 'konica minolta', 'eovi', 'eovi mcd mutuelle', 'aesio',
        'aésio mutuelle', 'smart good things', 'kelyps', 'kelyps intérim',
        'mister auto', 'mister-auto', 'markal', 'despinasse',
        'sacma', 'sacma agencements', 'alliance intérim'
    ]
    return player_names, full_name_players, distinctive_sponsors

ASSE_PLAYERS, ASSE_PLAYERS_FULL, ASSE_SPONSORS = load_asse_knowledge()

MAGIC_FANS_PATTERN = re.compile(
    r'\b(?:magic\s*[-]?\s*fans|magicfans|magics?\s*[-]?\s*91|mf\s*[-]?\s*91|mf\s*[-]?\s*1991)\b',
    re.IGNORECASE
)

MAGIC_FANS_NOISE_PATTERN = re.compile(
    r'\b(?:magic[\s:]*(?:the\s+)?gathering|the\s+gathering|mtg|wizards\s+of\s+the\s+coast|wotc|booster[s]?|play[- ]booster|deck[s]?|planeswalker|commander|hobbit|tolkien|middle[- ]earth|seigneur\s+des\s+anneaux|lord\s+of\s+the\s+rings|magic\s+johnson|orlando\s+magic|harry\s+potter|disney|winx|pokemon|pok[eé]mon|yu[- ]?gi[- ]?oh|campanilla|clochette|barbie|lego|playmobil|funko|kpop|bts|stray\s+kids|5\s+majeur|nba|basket|magic\s+system|cartes?\s+magic)\b',
    re.IGNORECASE
)

MAGIC_FANS_STICKER_PATTERN = re.compile(
    r'\b(autocollants?|stickers?|sticks?|adh[eé]sifs?)\b',
    re.IGNORECASE
)

# Rétrocompatibilité nom de variable historique
MAGIC_FANS_COLLECTOR_PATTERN = MAGIC_FANS_PATTERN

def is_magic_fans_collector_match(text, price_str=None):
    """
    Détecte tous les accessoires, écharpes, vêtements et collectors Magic Fans / MF91.
    Règle utilisateur : tous les articles Magic Fans ou MF91 qui coûtent moins de 80€.
    Exclut le bruit hors-sujet (Magic The Gathering, NBA Orlando, Disney, etc.) et les autocollants/stickers.
    """
    if not text:
        return False, ""
    import unicodedata
    t_norm = ''.join(c for c in unicodedata.normalize('NFD', str(text)) if unicodedata.category(c) != 'Mn')
    t_norm = re.sub(r'\s+', ' ', t_norm)

    # Couper les blocs de spam de visibilité / mots-clés dans les descriptions
    t_norm = re.split(r'\b(?:pour\s+la\s+visibilit[eé]|pour\s+le\s+r[eé]f[eé]rencement|mots?[- ]cl[eé]s?|(?:hash)?tags?\s*:)', t_norm, flags=re.IGNORECASE)[0]

    # Rejeter formellement les fanions, drapeaux, bannières, oriflammes (l'utilisateur ne veut pas de fanions)
    if re.search(r'\b(fanions?|drapeaux?|banni[eè]res?|oriflammes?|foulards?)\b', t_norm, re.IGNORECASE):
        if not re.search(r'\b(maillot|jersey|t-?shirt|echarpe|écharpe|sweat|hoodie|livre|fanzine)\b', t_norm, re.IGNORECASE):
            return False, "Exclusion fanion / drapeau"

    # Rejeter les vêtements de ville / prêt-à-porter non-supporters (chemises, costumes, cravates...) et marques de mode
    if re.search(r'\b(chemise|chemisette|cravate|costume|blazer|jupe|robe|mocassins?|escarpins?)\b', t_norm, re.IGNORECASE):
        if not re.search(r'\b(maillot|jersey|t-?shirt|echarpe|écharpe|veste|sweat|hoodie)\b', t_norm, re.IGNORECASE):
            return False, "Vêtement de ville non-supporter"
    if re.search(r'\b(ralph\s+lauren|polo\s+ralph|tommy\s+hilfiger|celio|jules|zara|h&m|massimo\s+dutti)\b', t_norm, re.IGNORECASE):
        return False, "Marque prêt-à-porter de ville"

    # Rejeter les autocollants / stickers / sticks (demande utilisateur explicite)
    if MAGIC_FANS_STICKER_PATTERN.search(t_norm):
        if not re.search(r'\b(maillot|jersey|echarpe|écharpe|veste|pull|sweat|bonnet|bob|casquette|livre|fanzine)\b', t_norm, re.IGNORECASE):
            return False, "Exclusion autocollant / sticker"

    # Rejeter le bruit hors-sujet
    if MAGIC_FANS_NOISE_PATTERN.search(t_norm):
        return False, ""

    # Rejeter formellement si un club rival ou un groupe adverse est mentionné
    is_conf, conf_team = is_conflicting_team(t_norm)
    if is_conf:
        return False, f"Club concurrent : {conf_team}"

    is_conf_grp, conf_grp = is_conflicting_supporter_group(t_norm)
    if is_conf_grp:
        return False, f"Groupe supporter adverse : {conf_grp}"

    m = MAGIC_FANS_PATTERN.search(t_norm)
    if not m:
        return False, ""

    # Plafond de prix : <= 80 € si fourni
    if price_str is not None:
        p_val = parse_price(price_str)
        if p_val is not None and p_val > 80.0:
            return False, f"Prix {p_val}€ > 80€"

    return True, m.group(0)

def is_asse_signal(text, is_filet=False):
    """
    Vérifie la présence d'un signal formel ASSE :
    1. 'ASSE' ou 'Saint-Étienne' (ou Sainté)
    2. Un joueur de la base ASSE 1980-2026 (ex: Khazri, Perrin, Stassin...)
    3. Un sponsor historique ou équipementier ASSE (ex: Manufrance, Dreamcast, Winamax...)
    4. Mots-clés verts / Chaudron / Geoffroy-Guichard / Forez
    5. Couleur verte (actif uniquement sur le flux Filet 'Maillot Asse')
    """
    if not text:
        return False, ""
    import unicodedata
    t_clean = ''.join(c for c in unicodedata.normalize('NFD', text) if unicodedata.category(c) != 'Mn').lower()
    t_clean = t_clean.replace('’', "'")

    # 0. Neutraliser les mentions d'adversaires où l'ASSE est l'équipe affrontée (ex: 'contre l'ASSE', 'face à Saint-Étienne')
    asse_opponent_pattern = r'\b(?:contre|vs\.?|face\s+[àa]|oppos[eé][es]?\s+[àa]|match\s+contre|jou[eé]\s+contre|match\s+face\s+[àa])\s+(?:l[\'\s]*)?(?:equipe\s+de\s+)?(?:as\s+)?(?:saint[- \.]*etienne|asse|st[- \.]*etienne|sainte|verts?)\b'
    t_asse_clean = re.sub(asse_opponent_pattern, ' ', t_clean)

    # 1. ASSE / Saint-Étienne / Sainté / A.S.S.E (sur texte nettoyé des mentions adversaires)
    non_foot_sainte = r'\bsainte[- ](?:barbe|marie|luce|croix|maxime|genevieve|adresse|claire|anne|rose|foy|helene)\b'
    if re.search(non_foot_sainte, t_asse_clean) and not re.search(r'\b(asse|saint[- \.]*etienne|st[- \.]*etienne)\b', t_asse_clean):
        pass
    else:
        asse_pattern = r'\b(asse|saint[- \.]*etienne|st[- \.]*etienne|sainte|a[\.\s\-]*s[\.\s\-]*saint[- \.]*etienne|a[\.\s\-]*s[\.\s\-]*st[- \.]*etienne)\b|(?:\b|^)a[\.\s\-]+s[\.\s\-]+s[\.\s\-]*e(?:\.|\b)'
        if re.search(asse_pattern, t_asse_clean):
            return True, "Mention explicite ASSE / Saint-Étienne"

    # 2. Sponsors & équipementiers historiques ASSE
    for sp in ASSE_SPONSORS:
        if re.search(r'\b' + re.escape(sp) + r'\b', t_clean):
            return True, f"Sponsor historique ({sp.title()})"

    # 2b. Équipementier Duarig (marque multi-clubs/amateurs : exige couleur verte ou contexte ASSE)
    if re.search(r'\bduarig\b', t_clean) and re.search(r'\b(vert|verte|verts|vertes)\b', t_clean):
        return True, "Équipementier Duarig (Vert)"

    # 3. Joueurs ASSE (1980-2026 - noms complets requis pour prénoms communs)
    for p_full_key, p_full_val in ASSE_PLAYERS_FULL.items():
        if p_full_key in t_clean:
            return True, f"Joueur ({p_full_val})"

    for p_last, p_full in ASSE_PLAYERS.items():
        if re.search(r'\b' + re.escape(p_last) + r'\b', t_clean):
            return True, f"Joueur ({p_full})"

    # 3b. Initiale + point + nom de joueur ASSE (en mode Filet / inspection description)
    if is_filet:
        for m_init in re.finditer(r'\b([a-z])\s*\.\s*([a-z]{4,})\b', t_clean):
            init_letter, last_name = m_init.group(1), m_init.group(2)
            if last_name in ASSE_PLAYERS and ASSE_PLAYERS[last_name].lower().startswith(init_letter):
                return True, f"Joueur initiales ({ASSE_PLAYERS[last_name]})"
            for full_p, full_label in ASSE_PLAYERS_FULL.items():
                if full_p.startswith(init_letter) and full_p.split()[-1] == last_name:
                    return True, f"Joueur initiales ({full_label})"

    # 4. Mots-clés club / Chaudron / Forez / Peuple Vert / Les Verts
    for kw in ['chaudron', 'geoffroy guichard', 'geoffroy-guichard', 'forez', 'peuple vert', 'allez les verts', 'les verts', 'des verts']:
        if kw in t_clean:
            return True, f"Mot-clé ({kw.title()})"

    return False, ""

def is_flux_smart_candidate(title_str):
    """
    Détecte en mémoire (<0.01ms) si une annonce du Flux Direct Foot mérite
    une inspection asynchrone de sa description en tâche de fond (Queue) :
    1. Présence d'une initiale + nom de joueur (ex: 'J. Clement', 'L. Perrin')
    2. Titre avec couleur verte (vert, green) sans club rival
    3. Titre neutre court de football (ex: 'Maillot de foot', 'Maillot vintage', 'T-shirt collector')
    4. Termes / sponsors club (Chaudron, Geoffroy-Guichard, Forez, Manufrance...)
    """
    if not title_str:
        return False, ""
    import unicodedata
    t_clean = ''.join(c for c in unicodedata.normalize('NFD', title_str) if unicodedata.category(c) != 'Mn').lower()
    t_clean = t_clean.replace('’', "'")

    # Éliminer d'emblée les sports non-football
    if re.search(r'\b(ciclismo|cyclisme|velo|radsport|gymshark|fitness|running|trail|basket|nba|nfl|rugby|bici)\b', t_clean):
        return False, ""

    # 1. Initiale + nom de joueur (ex: 'j. clement', 'l. perrin', 's. ruffier' - scan de toutes les occurrences)
    for m_init in re.finditer(r'\b([a-z])\s*\.\s*([a-z]{4,})\b', t_clean):
        init_letter, last_name = m_init.group(1), m_init.group(2)
        if last_name in ASSE_PLAYERS and ASSE_PLAYERS[last_name].lower().startswith(init_letter):
            return True, f"Joueur initiales ({ASSE_PLAYERS[last_name]})"
        for full_p, full_label in ASSE_PLAYERS_FULL.items():
            if full_p.startswith(init_letter) and full_p.split()[-1] == last_name:
                return True, f"Joueur initiales ({full_label})"

    # 2. Couleur verte dans un vêtement foot / sport (sans club rival)
    if re.search(r'\b(vert|verte|verts|vertes|green)\b', t_clean):
        if re.search(r'\b(maillots?|jerseys?|trikots?|camisetas?|maglias?|tenues?|t[- ]?shirts?|tee[- ]?shirts?|shirts?|hauts?)\b', t_clean):
            return True, "Couleur verte"

    # 3. Titre neutre minimaliste de football (nettoie la ponctuation et accepte 1 à 3 qualificatifs + tailles M..4XL)
    t_words = re.sub(r'[\.,;!\?\-\(\)\[\]/\:]+', ' ', t_clean)
    t_words = re.sub(r'\s+', ' ', t_words).strip()
    neutral_foot_pat = (
        r'^(?:maillots?|jerseys?|t[- ]?shirts?|tee[- ]?shirts?)'
        r'(?:\s+(?:de\s+foot(?:ball)?|foot(?:ball)?|sport|vintage|collector|match|ancien|retro|porte|prepare|officiel|authentique|domicile|exterieur|gardien|pro)){1,3}'
        r'(?:\s+(?:taille\s+[a-z0-9/]+|[0-9]?[smlxl]{1,4}|[0-9]{2,4}))?$'
    )
    if re.search(neutral_foot_pat, t_words):
        return True, "Titre neutre football"

    # 4. Termes du club / Forez / Chaudron / Manufrance
    if re.search(r'\b(chaudron|geoffroy[- ]guichard|forez|manufrance)\b', t_clean):
        return True, "Terme club / Forez"

    return False, ""

# Équipementiers tiers incompatibles avec l'ASSE (n'ont jamais équipé le club)
INCOMPATIBLE_KIT_BRANDS = [
    r'\blegea\b',
    r'\bgivova\b',
    r'\berre[aà]\b',
    r'\bjoma\b',
    r'\bmacron\b'
]
INCOMPATIBLE_KIT_PATTERN = re.compile(r'|'.join(INCOMPATIBLE_KIT_BRANDS), re.IGNORECASE)

def is_incompatible_kit_brand(brand_str="", title_str="", desc_str=""):
    """
    Bloque les maillots d'équipementiers tiers qui n'ont jamais équipé l'ASSE :
    LEGEA, Givova, Erreà, Joma, Macron.
    """
    b = (brand_str or "").strip()
    if b and b.upper() != "N/A":
        m = INCOMPATIBLE_KIT_PATTERN.search(b)
        if m:
            brand_name = m.group(0).lower()
            if brand_name in ('errea', 'erreà'):
                display_name = 'Erreà'
            elif brand_name == 'legea':
                display_name = 'LEGEA'
            elif brand_name == 'givova':
                display_name = 'Givova'
            elif brand_name == 'joma':
                display_name = 'Joma'
            elif brand_name == 'macron':
                display_name = 'Macron'
            else:
                display_name = brand_name.capitalize()
            return True, f"Équipementier incompatible ({display_name})"

    t = (title_str or "").strip()
    if t:
        m = INCOMPATIBLE_KIT_PATTERN.search(t)
        if m:
            brand_name = m.group(0).lower()
            if brand_name in ('errea', 'erreà'):
                display_name = 'Erreà'
            elif brand_name == 'legea':
                display_name = 'LEGEA'
            elif brand_name == 'givova':
                display_name = 'Givova'
            elif brand_name == 'joma':
                display_name = 'Joma'
            elif brand_name == 'macron':
                display_name = 'Macron'
            else:
                display_name = brand_name.capitalize()
            return True, f"Équipementier incompatible ({display_name})"

    return False, ""

def is_excluded_product(title_str="", desc_str="", price_str=""):
    """
    Filtre les articles indésirables avec zéro faux positif sur les vrais maillots :
    1. Plafond de prix à 350 € max
    2. Mugs, tasses, bols, chopes
    3. Cartes Panini, stickers, vignettes, topps
    4. Magnets, magnettes, aimants
    5. Vestes, blousons, doudounes
    6. Spam de mots-clés multi-clubs (> 4 clubs cités sans mention explicite ASSE)
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

    # 3. Panini / Stickers / Vignettes / Topps / Trading cards / Autocollants / Sticks
    card_pattern = r'\b(panini|stickers?|sticks?|autocollants?|adh[eé]sifs?|vignettes?|topps|adrenalyn|trading\s*cards?)\b'
    if re.search(card_pattern, t):
        return True, "Panini / Sticker / Autocollant"
    if d and re.search(card_pattern, d):
        if not re.search(r'\b(maillot|jersey|veste|tenue|ensemble)\b', t):
            return True, "Panini / Sticker / Autocollant"

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

    # 6. Photos, posters, affiches, cadres, tableaux, lithographies
    photo_pattern = r'\b(photo|photos|photographie|photographies|clich[eé]|clich[eé]s|poster|posters|affiche|affiches|cadre|cadres|tableau|tableaux|toile|toiles|lithographie|lithographies|tirage[s]?\s+photo)\b'
    if re.search(photo_pattern, t):
        if not re.search(r'\b(maillot|jersey)\b', t):
            return True, "Photo / Poster / Cadre"

    # 7. Livres, magazines, revues, journaux, DVD, VHS, BD (exclut systématiquement dans le titre, y compris 'Magazine Maillot Vert')
    media_pattern = r'\b(livre|livres|magazine|magazines|revue|revues|journal|journaux|gazette|gazettes|dvd|vhs|cassette|cassettes|bd|bande[ -]dessin[eé]e)\b'
    if re.search(media_pattern, t):
        return True, "Livre / Magazine / Journal"
    if d and re.search(media_pattern, d):
        if not re.search(r'\b(maillot|jersey|tenue|ensemble)\b', t):
            return True, "Livre / Magazine / Journal"

    # 7b. Programme de match / Revue officielle ASSE intitulée 'Maillot Vert' (sans le mot 'magazine')
    # Ex: 'ASSE – Maillot Vert – n° 33 - 2020', 'ASSE Maillot Vert n° 32 du 25/01/2020' ou 'ASSE –Maillot Vert – 2019'
    mv_mag_pattern = (
        r'\bmaillot\s+vert\b[\s–\-\—:]*'
        r'(?:(?:n[°oº]|num[eé]ro|#)\s*\d+\s*(?:du\s+\d{1,2}[/\-\.]\d{1,2}|[–\-\—]\s*(?:19|20)\d{2}\b)'
        r'|hors[- ]s[eé]rie\b)'
        r'|\b(?:programme|hebdo|hebdomadaire|mensuel|parution|exemplaire|revue|abonnement)\s+maillot\s+vert\b'
        r'|^asse\s*[–\-\—]+\s*maillot\s+vert\s*[–\-\—]+\s*(?:19|20)\d{2}\s*$'
    )
    if re.search(mv_mag_pattern, t) or (d and re.search(mv_mag_pattern, d)):
        return True, "Programme / Magazine 'Maillot Vert'"
    if re.search(r'\bmaillot\s+vert\b', t) and d and re.search(r'\b(revue|mensuel|hebdomadaire|num[eé]ros?|parution|abonnement)\b', d):
        return True, "Programme / Magazine 'Maillot Vert'"

    # 8. Fanions, drapeaux, bannières, écharpes, foulards
    flag_pattern = r'\b(fanion|fanions|drapeau|drapeaux|banni[eè]re|banni[eè]res|oriflamme|oriflammes|echarpe|écharpe|echarpes|écharpes|foulard|foulards)\b'
    if re.search(flag_pattern, t):
        if not re.search(r'\b(maillot|jersey)\b', t):
            return True, "Fanion / Drapeau / Écharpe"

    # 9. Porte-clés / Porte-clefs (exclut systématiquement dans le titre, y compris en forme de maillot)
    keychain_pattern = r'\b(porte[- ]cl[eé]s?|porte[- ]clefs?)\b'
    if re.search(keychain_pattern, t):
        return True, "Porte-clés"
    if d and re.search(keychain_pattern, d):
        if not re.search(r'\b(maillot|jersey|veste|tenue|ensemble)\b', t):
            return True, "Porte-clés"

    # 10. Figurines, statuettes, peluches, goodies, fèves, pin's, badges, calendriers, téléphonie, Funko Pop
    goodies_pattern = r'\b(funko|funko\s*pops?|pop\s+football|corinthian|microstars|soccerstarz|figurine|figurines|statuette|statuettes|statue|statues|peluche|peluches|doudou|doudous|poup[eé]e|poup[eé]es|gorille|panth[eè]re|mascotte|mascottes|f[eé]ve|f[eé]ves|pin\'?s|badge|badges|porte[- ]monnaie|portefeuille|calendrier|calendriers|almanach|puzzle|puzzles|support[- ]t[eé]l[eé]phone|porte[- ]t[eé]l[eé]phone|coque[s]?\s+(?:de\s+)?t[eé]l[eé]phone|coque[s]?\s+iphone|coque[s]?\s+smartphone|chargeur|chargeurs)\b'
    if re.search(goodies_pattern, t):
        if not re.search(r'\b(maillot\s+port[eé]|maillot\s+match)\b', t):
            return True, "Goodies / Figurine / Funko Pop"
    if d and re.search(r'\b(funko|funko\s*pops?|corinthian|microstars|figurine[s]?|statuette[s]?|statue[s]?|peluche[s]?|doudou[s]?|poup[eé]e[s]?|gorille|porte[- ]t[eé]l[eé]phone|support[- ]t[eé]l[eé]phone|coque[s]?\s+(?:de\s+)?t[eé]l[eé]phone|coque[s]?\s+iphone|coque[s]?\s+smartphone|chargeur)\b', d):
        if not re.search(r'\b(maillot|jersey|tenue|ensemble|t-?shirt|haut)\b', t):
            return True, "Goodies / Figurine / Accessoire (non-textile)"

    # 11. Casquettes, bonnets, bobs, chapeaux
    headwear_pattern = r'\b(casquette|casquettes|bonnet|bonnets|bob|bobs|chapeau|chapeaux|b[eé]ret|b[eé]rets)\b'
    if re.search(headwear_pattern, t):
        if not re.search(r'\b(maillot|jersey)\b', t):
            return True, "Casquette / Bonnet"

    # 12. Maillots de bain, bikinis, swimwear
    swim_pattern = r'\b(maillot\s+de\s+bain|bikini|swimwear)\b'
    if re.search(swim_pattern, t) or re.search(swim_pattern, d):
        return True, "Maillot de bain"

    # 13. Vestes, blousons, doudounes, parkas, coupe-vents
    jacket_pattern = r'\b(veste|vestes|blouson|blousons|doudoune|doudounes|parka|parkas|coupe[- ]vent|k[- ]?way|anorak)\b'
    if re.search(jacket_pattern, t):
        if not re.search(r'\b(maillot|jersey)\b', t):
            return True, "Veste / Blouson"
    if d and re.search(jacket_pattern, d):
        if not re.search(r'\b(maillot|jersey)\b', t):
            return True, "Veste / Blouson"

    # 14. Spam de mots-clés / Tag stuffing multi-clubs
    full_text = f"{t} {d}"
    clubs_in_title = {ck for ck, cp in CLUB_PATTERNS.items() if re.search(cp, t)}
    clubs_total = {ck for ck, cp in CLUB_PATTERNS.items() if re.search(cp, full_text)}

    # Si 3 clubs ou plus sont cités dans le titre seul -> spam évident
    if len(clubs_in_title) >= 3:
        return True, f"Spam multi-clubs dans le titre ({len(clubs_in_title)} clubs cités)"

    if len(clubs_total) > 4:
        if not is_explicit_asse_jersey(t, d):
            return True, f"Spam multi-clubs ({len(clubs_total)} clubs cités sans mention explicite ASSE)"

    # 15. Bas de sport seuls (shorts, pantalons, joggings, chaussettes) sans mention de maillot/jersey/tenue
    pants_pattern = r'\b(short|shorts|pantalon|pantalons|jogging|joggings|surv[eê]tement|surv[eê]tements|chaussette|chaussettes|bas\s+de\s+foot)\b'
    if re.search(pants_pattern, t):
        if not re.search(r'\b(maillot|jersey|tenue|ensemble|t-?shirt|haut)\b', t):
            return True, "Bas de sport / Short seul"

    # 16. Vêtements hors-sujet / Danse / Lingerie / Féminin non-sport (pole dance, paillettes, robes, jupes, etc.)
    offtopic_pattern = r'\b(poledance|pole\s+dance|paillette|paillettes|paillet[ée]s?|lingerie|soutien[- ]gorge|brassi[eè]re|robe|robes|jupe|jupes|dentelle|dentelles|escarpins?|talons?|maquillage|combishort)\b'
    if re.search(offtopic_pattern, t) or (d and re.search(offtopic_pattern, d)):
        return True, "Vêtement hors-sujet (danse/lingerie/robe)"

    # 17. Mots-clés personnalisés ajoutés en direct via le Dashboard
    custom_keywords = load_blacklisted_keywords()
    if custom_keywords:
        for kw in custom_keywords:
            kw_pat = r'\b' + re.escape(kw) + r'\b'
            if re.search(kw_pat, t) or (d and re.search(kw_pat, d)):
                return True, f"Mot-clé bloqué ({kw})"

    # 18. Sports hors-football (rugby, basket, NBA, NFL, etc.) et vêtements non sportifs (blouse, pull, chemisier, gilet)
    off_clothing = r'\b(rugby|rct|top\s*14|six\s*nations|basket|basketball|nba|wnba|nfl|baseball|mlb|hockey|nhl|blouse|blouses|chemisier|chemisiers|pull|pulls|gilet|gilets|cardigan|cardigans)\b'
    if re.search(off_clothing, t):
        if not is_asse_jersey_match(t):
            return True, "Sport hors-football ou vêtement non sportif (rugby/basket/nba/pull)"
    if d and re.search(off_clothing, d):
        if not is_asse_jersey_match(t) and not is_asse_jersey_match(d):
            return True, "Sport hors-football ou vêtement non sportif (rugby/basket/nba/pull)"

    # 19. Mangas, animés, esports, fiction (Captain Tsubasa, Olive et Tom, Inazuma, Blue Lock)
    anime_pattern = r'\b(captain\s+tsubasa|tsubasa|olive\s+et\s+tom|inazuma|blue\s+lock)\b'
    if re.search(anime_pattern, t) or (d and re.search(anime_pattern, d)):
        if not is_asse_jersey_match(t):
            return True, "Fiction / Animé (Captain Tsubasa/Manga)"

    # 20. Arbitres / Arbitrage (maillots d'arbitre génériques non-club)
    ref_pattern = r'\b(arbitre|arbitres|referee|referees|arbitrage)\b'
    if re.search(ref_pattern, t) or (d and re.search(ref_pattern, d)):
        if not is_asse_jersey_match(t):
            return True, "Maillot d'arbitre (non-club)"

    # 21. Cyclisme / Vélo / Tour de France / Radsport (verrouillage strict)
    cycling_pat = r'\b(cyclis(?:me|te|tes)|v[eé]lo|v[eé]los|tour\s+de\s+france|letour|peloton|skoda|bicyclette|santini|castelli|uci|giro|giro\s+d[\'\s]italia|vuelta|cuissard|cuissards|vtt|radsport|rennrad|rennradtrikot|fahrrad|cycling|ciclismo|bici)\b'
    is_cycl_t = bool(re.search(cycling_pat, t))
    is_cycl_d = bool(d and re.search(cycling_pat, d))
    if is_cycl_t or is_cycl_d:
        # Bloqué dans tous les cas SAUF si le titre précise formellement du football (ex: 'maillot foot asse')
        has_foot = bool(re.search(r'\b(foot|football)\b', t))
        if not (has_foot and is_asse_jersey_match(t)):
            return True, "Cyclisme / Vélo / Radsport (non-football)"

    # 22. Running, Trail, Marathon, Sainté-Lyon, Course à pied (hors football)
    running_pat = r'\b(saint[eé][- ]?lyon|course\s+(?:[aà]\s+)?pied|ultra[- ]trail|marathon|semi[- ]marathon|triathlon)\b'
    if re.search(running_pat, t):
        if not (is_asse_jersey_match(t) and re.search(r'\b(foot|football)\b', t)):
            return True, "Course à pied / Trail / Sainté-Lyon (non-football)"
    if d and re.search(r'\b(saint[eé][- ]?lyon|course\s+(?:[aà]\s+)?pied)\b', d):
        if not (is_asse_jersey_match(t) and re.search(r'\b(maillot|jersey)\b', t)):
            return True, "Course à pied / Sainté-Lyon (non-football)"

    # 23. PLV, présentoirs, mobilier de magasin, cartons publicitaires
    plv_pattern = r'\b(plv|pr[eé]sentoir|pr[eé]sentoirs|stand|vitrine|vitrines|totem|totems|panneau\s+publicitaire)\b'
    if re.search(plv_pattern, t):
        if not re.search(r'\b(maillot\s+port[eé]|maillot\s+match)\b', t):
            return True, "PLV / Présentoir publicitaire"
    if d and re.search(plv_pattern, d):
        if not re.search(r'\b(maillot|jersey|tenue|ensemble)\b', t):
            return True, "PLV / Présentoir publicitaire"

    # 24. Chaussures de football, crampons, protège-tibias
    cleats_pattern = r'\b(crampon|crampons|chaussure[s]?\s+de\s+foot|chaussure[s]?\s+de\s+football|prot[eè]ge[- ]tibia[s]?)\b'
    if re.search(cleats_pattern, t):
        if not re.search(r'\b(maillot|jersey|tenue|ensemble)\b', t):
            return True, "Crampons / Chaussures de foot"
    if d and re.search(cleats_pattern, d):
        if not re.search(r'\b(maillot|jersey|tenue|ensemble)\b', t):
            return True, "Crampons / Chaussures de foot"

    # 25. Négation explicite ("no maillot")
    if re.search(r'\bno\s+(?:de\s+)?(?:maillot|jersey)\b', t):
        return True, "Négation explicite (no maillot)"

    # 26. Porte-manteaux, patères, cintres
    coathanger_pattern = r'\b(porte[- ]manteau[x]?|pat[eè]re[s]?)\b'
    if re.search(coathanger_pattern, t):
        return True, "Porte-manteau / Patère"
    if re.search(r'\bcintre[s]?\b', t) and not re.search(r'\b(maillot\s+port[eé]|maillot\s+match)\b', t):
        return True, "Cintre"
    if d and re.search(coathanger_pattern, d):
        if not re.search(r'\b(maillot|jersey|tenue|ensemble)\b', t):
            return True, "Porte-manteau / Patère"

    # 27. Maillot adverse porté contre l'ASSE (l'ASSE est uniquement citée comme adversaire de la rencontre)
    # Ex: 'Maillot MHSC de Benjamin Lecomte porté un match contre l’AS Saint-Étienne'
    import unicodedata
    full_text = f"{t} {d}"
    full_text_norm = ''.join(c for c in unicodedata.normalize('NFD', full_text) if unicodedata.category(c) != 'Mn').lower().replace('’', "'")
    asse_opp_pattern = r'\b(?:contre|vs\.?|face\s+[àa]|oppos[eé][es]?\s+[àa]|match\s+contre|jou[eé]\s+contre|match\s+face\s+[àa])\s+(?:l[\'\s]*)?(?:equipe\s+de\s+)?(?:as\s+)?(?:saint[- \.]*etienne|asse|st[- \.]*etienne|sainte|verts?)\b'
    if re.search(asse_opp_pattern, full_text_norm):
        full_text_stripped = re.sub(asse_opp_pattern, ' ', full_text_norm)
        asse_standalone_pat = r'\b(asse|saint[- \.]*etienne|st[- \.]*etienne|sainte)\b|(?:\b|^)a[\.\s\-]+s[\.\s\-]+s[\.\s\-]*e(?:\.|\b)'
        if not re.search(asse_standalone_pat, full_text_stripped):
            return True, "Maillot adverse (porté contre l'ASSE)"

    # 28. Vêtements d'entraînement / Training / Échauffement / Pré-match (sauf si maillot de match officiel)
    training_pat = r'\b(entrainement|entraînement|training|echauffement|échauffement|pr[eé][- ]?(?:match|game)|prematch|pregame|pr[eé]game|avant[- ]match)\b'
    match_override = r'\b(domicile|ext[eé]rieur|away|third|fourth|gardien|goalkeeper|match\s*worn|match\s*issue|coupe\s+de\s+france|coupe\s+d[\'\s]?europe|port[eé]\s+par|pr[eé]par[eé]\s+par)\b'
    if re.search(training_pat, t):
        if not re.search(match_override, t):
            return True, "Vêtement d'entraînement / Training"
    if d and re.search(r'\b(?:maillot|t-?shirt|tee-?shirt|haut|tenue|veste|gamme|mod[eè]le|version)\s+(?:d[\'\s]?|de\s+)?(?:entrainement|entraînement|training|echauffement|échauffement|pr[eé][- ]?(?:match|game)|prematch|pregame|pr[eé]game|avant[- ]match)\b|\bcollection\s+training\b', d):
        if not re.search(match_override, t) and not re.search(match_override, d):
            return True, "Vêtement d'entraînement / Training"

    # 29. T-shirts et vêtements 100% Coton / Lifestyle / Casual (non maillots de match)
    coton_pat = r'\b(100\s*%\s*coton|100\s*%\s*cotton|mati[eè]re\s+coton|pur\s+coton|pure\s+cotton)\b'
    if re.search(coton_pat, t):
        if not re.search(match_override, t):
            return True, "Vêtement 100% coton / Casual"
    if d and re.search(coton_pat, d):
        if re.search(r'\b(t-?shirt|tee-?shirt)\b', t) and not re.search(r'\b(maillot|jersey)\b', t):
            if not re.search(match_override, t) and not re.search(match_override, d):
                return True, "T-shirt 100% coton (non-maillot)"

    # 30. Exclusion intégrale Sainte-Barbe (maillots, t-shirts, polos et produits dérivés compris)
    sainte_barbe_pat = r'\b(sainte[- ]barbe|ste[- ]barbe)\b'
    if re.search(sainte_barbe_pat, t) or (d and re.search(sainte_barbe_pat, d)):
        return True, "Édition / Produit Sainte-Barbe"

    # 31. Rééditions, remakes et reproductions non d'époque
    reedition_neg_pat = r'\b(?:pas\s+une?|pas\s+de|non|ce\s+n[\'\s]?est\s+pas\s+une?|aucunement|rien\s+[àa]\s+voir\s+avec\s+(?:une?|les)?|pas\s+un|sans)\s+(?:r[eé][- ]?[eé]dition[s]?|remake[s]?|repro(?:duction)?s?)\b'
    full_reed = f"{t} {d}"
    cleaned_reed = re.sub(reedition_neg_pat, ' ', full_reed, flags=re.IGNORECASE)
    reedition_pat = r'\b(r[eé][- ]?[eé]dition[s]?|remake[s]?|reproduction[s]?)\b'
    if re.search(reedition_pat, cleaned_reed, re.IGNORECASE):
        return True, "Réédition / Reproduction non d'époque"

    # 32. Réédition Duarig Manufrance (anachronisme historique : Manufrance 1970s réédité par Duarig 2000s)
    # Ex: 'Maillot asse manufrance duarig XL'
    if re.search(r'\bmanufrance\b', full_reed) and re.search(r'\bduarig\b', full_reed):
        return True, "Réédition Manufrance Duarig (anachronisme)"

    # 33. Équipementiers incompatibles avec l'ASSE (LEGEA, Givova, Erreà, Joma, Macron)
    is_bad_kit, bad_kit_reason = is_incompatible_kit_brand("", title_str)
    if is_bad_kit:
        return True, bad_kit_reason

    return False, "OK"

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

def log(message, to_error_log=None):
    """Log avec timestamp heure de Paris et persistance automatique des erreurs"""
    timestamp = get_paris_time().strftime('%Y-%m-%d %H:%M:%S')
    formatted = f"[{timestamp}] {message}"
    print(formatted, flush=True)

    if to_error_log is False:
        return

    should_record = to_error_log is True or (
        message.lstrip().startswith(("⚠️", "🚨", "❌")) or "WATCHDOG" in message
    )
    if should_record:
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

def record_tracked_item(item_data):
    """Enregistre un nouvel article pour le suivi individuel du cycle de vie"""
    try:
        lock_path = TRACKED_ITEMS_FILE + ".lock"
        with open(lock_path, "a") as lf:
            fcntl.flock(lf, fcntl.LOCK_EX)
            try:
                data = {}
                if os.path.exists(TRACKED_ITEMS_FILE):
                    try:
                        with open(TRACKED_ITEMS_FILE, "r", encoding="utf-8") as f:
                            data = json.load(f)
                    except Exception:
                        data = {}
                item_id_str = str(item_data["item_id"])
                data[item_id_str] = item_data
                tmp_file = TRACKED_ITEMS_FILE + f".tmp.{os.getpid()}"
                with open(tmp_file, "w", encoding="utf-8") as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
                os.replace(tmp_file, TRACKED_ITEMS_FILE)
            finally:
                fcntl.flock(lf, fcntl.LOCK_UN)
        log(f"🎯 [Tracker] Article #{item_data['item_id']} enregistré pour suivi de cycle de vie (Discord ID: {item_data.get('discord_message_id')})")
    except Exception as e:
        log(f"⚠️ Erreur enregistrement tracking #{item_data.get('item_id')}: {e}")

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

def fetch_item_description(item_url, item=None):
    """Récupère rapidement la description d'une annonce via une mini-requête HTTP optimisée avec retry silencieux"""
    if not item_url:
        return ""
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept-Language': 'fr-FR,fr;q=0.9',
    }
    for attempt in range(2):
        try:
            resp = requests.get(item_url, headers=headers, timeout=6)
            if resp.status_code == 200:
                resp.encoding = 'utf-8'
                html = resp.text
                if isinstance(item, dict):
                    item['_prefetched_html'] = html
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
        except requests.exceptions.Timeout:
            if attempt == 0:
                time.sleep(0.5)
                continue
            log("ℹ️ [Vinted] Latence réseau temporaire micro-fetch description", to_error_log=False)
        except Exception as e:
            log(f"ℹ️ [Vinted] Incident micro-fetch description: {e}", to_error_log=False)
            break
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
    """Extrait les articles avec Parsing Intelligent du Titre (V5.0 Ultra-Rapide Flash)"""
    try:
        items = page.evaluate("""
            async () => {
                let gridItems = document.querySelectorAll('div[class*="feed-grid__item"], [data-testid="grid-item"]');
                if (!gridItems || gridItems.length < 20) {
                    await new Promise(r => setTimeout(r, 250));
                    gridItems = document.querySelectorAll('div[class*="feed-grid__item"], [data-testid="grid-item"]');
                }
                if (!gridItems || gridItems.length === 0) return [];
                const items = [];
                const maxToExtract = 48; // Buffer de sécurité blindé pour les heures de pointe (48 vraies annonces)
                const count = Math.min(gridItems.length, maxToExtract);
                
                for (let idx = 0; idx < count; idx++) {
                    const el = gridItems[idx];
                    try {
                        const link = el.querySelector('a');
                        if (!link) continue;
                        
                        const url = link.href;
                        const idMatch = url.match(/items\\/(\\d+)/);
                        if (!idMatch) continue;
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
                }
                return items;
            }
        """)
        return items
    except Exception as e:
        log(f"❌ Erreur extraction liste: {e}")
        return []

in_flight_alert_ids = set()

def send_telegram_alert(item_id, title, price, size, brand, status, seller, photo_url, desc_clean, item_url, buy_url, is_mf=False):
    """Envoie une alerte Telegram ultra-réactive (<100ms) avec bouton d'achat direct en 1 clic"""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return None

    tag = "🟢 [Magic Fans]" if is_mf else "🟢 [Vinted]"
    clean_title_html = (title or "Maillot ASSE").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    caption_lines = [
        f"{tag} <b>{clean_title_html}</b>\n",
        f"💰 Prix : <b>{price}</b> | 📏 Taille : <b>{size}</b>",
        f"🏷️ Marque : <b>{brand}</b> | État : <b>{status}</b>",
    ]
    if seller:
        caption_lines.append(f"👤 Vendeur : <b>{seller}</b>")
    if desc_clean:
        clean_desc = desc_clean[:220].replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").strip()
        if len(desc_clean) > 220:
            clean_desc += "..."
        caption_lines.append(f"\n📖 <i>\"{clean_desc}\"</i>")

    caption = "\n".join(caption_lines)

    reply_markup = {
        "inline_keyboard": [
            [
                {
                    "text": f"⚡ ACHETER EN 1 CLIC ({price})",
                    "url": buy_url
                }
            ],
            [
                {
                    "text": "🔍 Voir la fiche sur Vinted",
                    "url": item_url
                }
            ]
        ]
    }

    tg_url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendPhoto"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "photo": photo_url or "https://images.vinted.net/assets/icon-76x76-precomposed-3e6e4c5f0b8c7e5a5c5e5e5e5e5e5e5e.png",
        "caption": caption,
        "parse_mode": "HTML",
        "reply_markup": reply_markup,
        "disable_notification": True
    }

    try:
        r = requests.post(tg_url, json=payload, timeout=6)
        if r.status_code == 200:
            msg_id = r.json().get("result", {}).get("message_id")
            log(f"✅ [Telegram] Alerte #{item_id} envoyée (Msg ID: {msg_id})")
            return msg_id
        else:
            log(f"⚠️ [Telegram] Erreur HTTP {r.status_code}: {r.text[:120]}")
    except Exception as e:
        log(f"⚠️ [Telegram] Exception: {e}")
    return None

def send_discord_alert(context, item, bypass_jersey_filters=False):
    """Envoie une alerte Discord & Telegram ultra-rapide (~0.3s) avec bouton 1-clic et photos HD"""
    if not DISCORD_WEBHOOK_URL and not TELEGRAM_BOT_TOKEN: return

    global alerted_ids, in_flight_alert_ids
    raw_id = item.get('id')
    try:
        int_id = int(raw_id)
    except (ValueError, TypeError):
        int_id = raw_id

    # VERROU ABSOLU ANTI-DOUBLON (Empêche strictement 2 alertes simultanées ou déjà envoyées)
    with state_lock:
        if int_id and (int_id in alerted_ids or int_id in in_flight_alert_ids):
            log(f"🛡️ [Anti-Doublon Absolu] Alerte déjà envoyée ou en cours pour #{int_id}, envoi bloqué !")
            return
        if int_id:
            in_flight_alert_ids.add(int_id)

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

        # Blocage absolu des clubs concurrents et groupes de supporters adverses dans le titre
        is_conf_t, conf_team_t = is_conflicting_team(final_title)
        if is_conf_t:
            log(f"🚫 [Vinted] Alerte bloquée (Club concurrent dans le titre : {conf_team_t}) : {final_title}")
            return

        is_conf_grp_t, conf_grp_t = is_conflicting_supporter_group(final_title)
        if is_conf_grp_t:
            log(f"🚫 [Vinted] Alerte bloquée (Groupe adverse dans le titre : {conf_grp_t}) : {final_title}")
            return

        # Rejeter le bruit hors-sujet et jeux de cartes (Magic The Gathering...)
        if MAGIC_FANS_NOISE_PATTERN.search(final_title):
            log(f"🚫 [Vinted] Alerte bloquée (Hors-sujet / Jeu de cartes dans le titre) : {final_title}")
            return
        if final_brand and re.search(r'\b(gathering|wizards|mtg)\b', final_brand, re.IGNORECASE):
            log(f"🚫 [Vinted] Alerte bloquée (Marque jeu de cartes : {final_brand}) : {final_title}")
            return

        # Bloquer les équipementiers incompatibles (LEGEA, Givova, Erreà, Joma, Macron)
        is_bad_brand, bad_brand_reason = is_incompatible_kit_brand(final_brand, final_title)
        if is_bad_brand:
            log(f"🚫 [Vinted] Alerte bloquée ({bad_brand_reason}) : {final_title} (Marque: {final_brand})")
            return

        is_mf_t, mf_kw_t = is_magic_fans_collector_match(final_title)
        is_asse_jersey_t = is_asse_jersey_match(final_title)
        if is_mf_t:
            p_val = parse_price(final_price)
            if not is_asse_jersey_t and p_val is not None and p_val > 80.0:
                log(f"🚫 [Vinted] Alerte Magic Fans non-maillot bloquée car prix ({p_val}€) > 80€ : {final_title}")
                return
            if p_val is None or p_val <= 80.0:
                bypass_jersey_filters = True

        # Filtrage des produits indésirables (Mug, Panini, Prix > 350€) sauf Collector Magic Fans
        if not bypass_jersey_filters:
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

        # Micro-fetch ultra-rapide HTTP (200-300ms) ou réutilisation instantanée (0ms) si déjà pré-chargé
        photos = [photo_url] if photo_url else []
        desc_clean = ""
        seller_name = item.get('seller', '')
        initial_fav_count = 0
        try:
            html = item.pop('_prefetched_html', None)
            if not html:
                headers = {
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                    'Accept-Language': 'fr-FR,fr;q=0.9',
                }
                resp = requests.get(item_url, headers=headers, timeout=2.5)
                if resp.status_code == 200:
                    resp.encoding = 'utf-8'
                    html = resp.text
            if html:

                # Extraction du nombre initial de favoris ❤️ (supporte JSON normal et échappé Next.js)
                m_fav = (
                    re.search(r'\\?"favourite_count\\?"\s*:\s*(\d+)', html)
                    or re.search(r"ajouté aux favoris par (\d+) utilisateur", html, re.I)
                )
                if m_fav:
                    try:
                        initial_fav_count = int(m_fav.group(1))
                    except ValueError:
                        initial_fav_count = 0

                # Exclusion des catégories Livres / Magazines / Presse / DVD (hors recherche Collector Magic Fans)
                if not bypass_jersey_filters:
                    m_cat = re.search(r'\\?"category\\?"\s*:\s*\\?"([^"\\]+)', html)
                    if m_cat:
                        cat_val = m_cat.group(1).lower()
                        if any(k in cat_val for k in ['livres', 'magazines', 'manuels', 'bande dessin', 'presse', 'dvd', 'jeux vid', 'musique', 'vinyles']):
                            log(f"🚫 [Vinted] Alerte filtrée (Catégorie Vinted non-textile : {m_cat.group(1)}) : {final_title}")
                            return

                # Récupération de secours de la taille / marque / état depuis le JSON de la fiche produit si N/A
                if final_size == 'N/A':
                    m_sz = re.search(r'\\?"code\\?"\s*:\s*\\?"size\\?"[^\}]{0,200}\\?"value\\?"\s*:\s*\\?"([^"\\]+)', html)
                    if m_sz and m_sz.group(1).strip():
                        final_size = clean_text(m_sz.group(1).strip())
                        if not bypass_jersey_filters and FILTER_ADULT_ONLY:
                            is_excl_sz, reason_sz = is_excluded_size(final_size, raw_title_val)
                            if is_excl_sz:
                                log(f"🚫 [Vinted] Alerte filtrée après lecture fiche ({reason_sz}) : {final_title} (Taille: {final_size})")
                                return
                if final_brand == 'N/A':
                    m_br = re.search(r'\\?"code\\?"\s*:\s*\\?"brand\\?"[^\}]{0,200}\\?"title\\?"\s*:\s*\\?"([^"\\]+)', html)
                    if m_br and m_br.group(1).strip():
                        final_brand = clean_text(m_br.group(1).strip())
                is_bad_brand, bad_brand_reason = is_incompatible_kit_brand(final_brand, final_title)
                if is_bad_brand:
                    log(f"🚫 [Vinted] Alerte filtrée après lecture fiche ({bad_brand_reason}) : {final_title} (Marque: {final_brand})")
                    return
                if final_status in ['N/A', 'Non spécifié']:
                    m_st = re.search(r'\\?"code\\?"\s*:\s*\\?"status\\?"[^\}]{0,200}\\?"value\\?"\s*:\s*\\?"([^"\\]+)', html)
                    if m_st and m_st.group(1).strip():
                        final_status = clean_text(m_st.group(1).strip())

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
                    # Tag stuffing / spam multi-clubs : toujours bloqué (y compris Magic Fans)
                    is_excl_spam, reason_spam = is_excluded_product(final_title, desc_clean, final_price)
                    if is_excl_spam and "Spam" in reason_spam:
                        log(f"🚫 [Vinted] Alerte bloquée ({reason_spam}) : {final_title}")
                        return

                    # Groupe adverse en description : toujours bloqué
                    is_conf_grp_d, conf_grp_d = is_conflicting_supporter_group(desc_clean)
                    if is_conf_grp_d:
                        log(f"🚫 [Vinted] Alerte bloquée (Groupe adverse en description : {conf_grp_d}) : {final_title}")
                        return

                    is_mf_d, mf_kw_d = is_magic_fans_collector_match(desc_clean)
                    if is_mf_d:
                        p_val = parse_price(final_price)
                        if not is_asse_jersey_t and not is_asse_jersey_match(desc_clean) and p_val is not None and p_val > 80.0:
                            log(f"🚫 [Vinted] Alerte Magic Fans non-maillot bloquée (description) car prix ({p_val}€) > 80€ : {final_title}")
                            return
                        if p_val is None or p_val <= 80.0:
                            bypass_jersey_filters = True
                    if not bypass_jersey_filters:
                        is_excl, reason = is_excluded_product(final_title, desc_clean, final_price)
                        if is_excl:
                            log(f"🚫 [Vinted] Alerte filtrée ({reason}) : {final_title} ({final_price})")
                            return
                        if FILTER_ADULT_ONLY:
                            is_excl_s, reason_s = is_excluded_size(final_size, raw_title_val, desc_clean)
                            if is_excl_s:
                                log(f"🚫 [Vinted] Alerte filtrée ({reason_s}) : {final_title} (Taille: {final_size})")
                                return

                    # Si le titre ne mentionne pas explicitement ASSE/Saint-Étienne (match via Joueur/Sponsor),
                    # vérifier que la description ne désigne pas un autre club concurrent
                    if not is_asse_jersey_match(final_title) and not is_asse_jersey_match(desc_clean):
                        is_conf_d, conf_d = is_conflicting_team(desc_clean)
                        if is_conf_d:
                            log(f"🚫 [Vinted] Alerte filtrée (Équipe concurrente dans la description : {conf_d}) : {final_title}")
                            return
        except Exception as e:
            log(f"⚠️ [Vinted] Micro-fetch fiche produit: {e}")

        buy_url = f"https://www.vinted.fr/transaction/buy/new?item_id={item_id}"

        # Description formatée pour Discord embed
        fav_line_init = f"❤️ **{initial_fav_count} favori{'s' if initial_fav_count > 1 else ''}** sur Vinted"
        fav_badge_init = f" • ❤️ {initial_fav_count} favori{'s' if initial_fav_count > 1 else ''}"
        description_text = f"⚡ **[ACHETER EN 1 CLIC ({final_price})]({buy_url})**\n\n💰 **{final_price}** | 📏 Taille: **{final_size}**\n🏷️ Marque: **{final_brand}** | État: **{final_status}**\n{fav_line_init}"
        if seller_name:
            description_text += f"\n👤 Vendeur: **{seller_name}**"
        if desc_clean:
            embed_desc_body = desc_clean[:400] + ("..." if len(desc_clean) > 400 else "")
            description_text += f"\n\n{embed_desc_body}"

        is_mf = is_magic_fans_collector_match(final_title)[0] or (bool(desc_clean) and is_magic_fans_collector_match(desc_clean)[0])
        tag_mf = "🟢 [Magic Fans] " if is_mf else ""

        embed1 = {
            "title": f"🔔 {tag_mf}{final_title}",
            "url": item_url,
            "description": description_text,
            "color": 0x1B5E20 if is_mf else 0x09B83E,
            "footer": {"text": f"Vinted Sniper • ID: {item_id}{fav_badge_init}"},
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

        notif_text = f"""@everyone | {tag_mf}{final_title}
💰 {final_price} | 📏 {final_size} | 🏷️ {final_brand}"""
        if desc_preview:
            notif_text += f"\n📝 {desc_preview}"

        payload1 = {
            "content": notif_text,
            "username": "Vinted ASSE Bot", 
            "avatar_url": "https://images.vinted.net/assets/icon-76x76-precomposed-3e6e4c5f0b8c7e5a5c5e5e5e5e5e5e5e.png", 
            "embeds": embeds_batch1
        }

        discord_msg_id = None
        telegram_msg_id = None
        sent_ok = False

        def _send_discord():
            if not DISCORD_WEBHOOK_URL:
                return None
            try:
                resp1 = requests.post(DISCORD_WEBHOOK_URL + "?wait=true", json=payload1, timeout=8)
                if resp1.status_code in [200, 204]:
                    try:
                        return resp1.json().get("id")
                    except Exception:
                        return "OK"
                else:
                    log(f"⚠️ Réponse Discord inhabituelle ({resp1.status_code}): {resp1.text[:100]}")
            except Exception as e_post:
                log(f"⚠️ Erreur envoi webhook Discord batch1: {e_post}")
            return None

        def _send_telegram():
            return send_telegram_alert(
                item_id=item_id,
                title=final_title,
                price=final_price,
                size=final_size,
                brand=final_brand,
                status=final_status,
                seller=seller_name,
                photo_url=photos[0] if photos else photo_url,
                desc_clean=desc_clean,
                item_url=item_url,
                buy_url=buy_url,
                is_mf=is_mf
            )

        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
            fut_d = executor.submit(_send_discord)
            fut_t = executor.submit(_send_telegram)
            discord_msg_id = fut_d.result()
            telegram_msg_id = fut_t.result()

        if discord_msg_id or telegram_msg_id:
            sent_ok = True

        if not sent_ok:
            with state_lock:
                in_flight_alert_ids.discard(int_id)
            return

        with state_lock:
            if int_id:
                alerted_ids.add(int_id)
                save_alerted_ids_cache(alerted_ids)
                in_flight_alert_ids.discard(int_id)

        # Si l'annonce contient plus de 10 photos (jusqu'à 20 photos au total) :
        # Envoi d'un 2ème lot 100% silencieux (flags: 4096 SUPPRESS_NOTIFICATIONS - aucune notif ni vibration)
        if DISCORD_WEBHOOK_URL and len(photos) > 10:
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

        log(f"✅ [Vinted] Alerte envoyée #{item_id} (Discord & Telegram actifs, achat 1-clic inclus)")

        # Enregistrement dans le tracker individuel de cycle de vie (1er pointage rapide à t + 3 min)
        now_ts = time.time()
        record_tracked_item({
            "item_id": str(item_id),
            "discord_message_id": discord_msg_id,
            "telegram_message_id": telegram_msg_id,
            "title": final_title,
            "price": final_price,
            "initial_price": final_price,
            "size": final_size,
            "brand": final_brand,
            "status_item": final_status,
            "seller": seller_name,
            "url": item_url,
            "photos": photos[:10] if photos else [],
            "description": description_text,
            "fav_count": initial_fav_count,
            "created_at": now_ts,
            "status": "ACTIVE",
            "check_count": 0,
            "last_checked_at": None,
            "next_check_at": now_ts + 180,
            "sold_at": None,
            "sold_duration_seconds": None,
            "sold_duration_str": None
        })

    except Exception as e:
        log(f"❌ Erreur Discord: {e}")
    finally:
        with state_lock:
            in_flight_alert_ids.discard(int_id)

_last_scan_heartbeat = time.time()

def update_watchdog_heartbeat():
    global _last_scan_heartbeat
    _last_scan_heartbeat = time.time()

def watchdog_thread_worker():
    """Surveille en continu l'activité du bot et force le redémarrage si aucun scan depuis 90s"""
    while True:
        time.sleep(15)
        elapsed = time.time() - _last_scan_heartbeat
        if elapsed > 90:
            timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            print(f"[{timestamp}] 🚨 WATCHDOG: Aucun scan depuis {int(elapsed)}s (bot figé) ! Redémarrage forcé...", flush=True)
            os._exit(1)

def watchdog_handler(signum, frame):
    """Tue le bot si un cycle prend trop de temps (Freeze detection)"""
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    print(f"[{timestamp}] 🚨 WATCHDOG: Bot figé depuis trop longtemps ! Redémarrage forcé...", flush=True)
    os._exit(1) # Sortie brutale pour forcer le redémarrage systemd

state_lock = threading.RLock()
flux_seen_ids = load_seen_ids_cache()
filet_seen_ids = load_filet_seen_ids_cache()
alerted_ids = load_alerted_ids_cache()
initialized_sources = set()
shared_last_seen_id = load_last_seen_id()
if flux_seen_ids:
    shared_last_seen_id = max(shared_last_seen_id, max(flux_seen_ids))

import queue
smart_inspection_queue = queue.Queue(maxsize=100)

def worker_smart_inspection():
    """
    Thread d'inspection asynchrone (Queue en tâche de fond) :
    - Inspecte discrètement (~1-2 requêtes/min max) la description des annonces 'candidates' du flux
    - Si la description contient 'ASSE' ou 'Saint-Étienne' ou un joueur, déclenche l'alerte immédiate
    - 0 impact sur la vitesse du sniper principal, 0 risque de blocage IP
    """
    log("🧠 [Smart-Inspector] Démarrage du thread d'inspection asynchrone en arrière-plan")
    while True:
        try:
            item, reason_candidate = smart_inspection_queue.get()
            item_id = item.get('id')
            item_url = item.get('url', f"https://www.vinted.fr/items/{item_id}")
            t_titre = item.get('title', '')
            t_prix = item.get('price', '')

            # Double vérification : si déjà alerté entre-temps
            with state_lock:
                if item_id in alerted_ids:
                    smart_inspection_queue.task_done()
                    continue

            log(f"🕵️ [Smart-Inspector] Inspection description pour #{item_id} ({reason_candidate}) : '{t_titre}'")
            desc = fetch_item_description(item_url, item=item)
            if desc:
                # Cas particulier : inspection Collector Magic Fans déportée hors du verrou principal
                if reason_candidate == "Magic Fans Collector":
                    is_c_t, c_team_t = is_conflicting_team(t_titre)
                    if is_c_t:
                        item.pop('_prefetched_html', None)
                        log(f"🚫 [Smart-Inspector] Article Magic Fans exclu (Club concurrent dans le titre : {c_team_t}) : '{t_titre}'")
                        smart_inspection_queue.task_done()
                        continue
                    is_c_g, c_grp_t = is_conflicting_supporter_group(t_titre)
                    if is_c_g:
                        item.pop('_prefetched_html', None)
                        log(f"🚫 [Smart-Inspector] Article Magic Fans exclu (Groupe adverse dans le titre : {c_grp_t}) : '{t_titre}'")
                        smart_inspection_queue.task_done()
                        continue
                    if MAGIC_FANS_STICKER_PATTERN.search(t_titre):
                        item.pop('_prefetched_html', None)
                        log(f"🚫 [Smart-Inspector] Article Magic Fans exclu (Autocollant / Sticker) : '{t_titre}'")
                        smart_inspection_queue.task_done()
                        continue
                    if MAGIC_FANS_NOISE_PATTERN.search(t_titre):
                        item.pop('_prefetched_html', None)
                        log(f"🚫 [Smart-Inspector] Article Magic Fans exclu (Bruit / Jeu de cartes dans le titre) : '{t_titre}'")
                        smart_inspection_queue.task_done()
                        continue
                    is_excl_sp, r_sp = is_excluded_product(t_titre, desc, t_prix)
                    if is_excl_sp:
                        is_allowed_collector = False
                        if "Fanion / Drapeau / Écharpe" in r_sp:
                            # N'autoriser que les vraies écharpes et bloquer formellement les fanions / drapeaux
                            if re.search(r'\b(echarpes?|écharpes?)\b', t_titre, re.I) and not re.search(r'\b(fanions?|drapeaux?|banni[eè]res?|oriflammes?|foulards?)\b', t_titre, re.I):
                                is_allowed_collector = True
                        elif "Livre" in r_sp:
                            if re.search(r'\b(livres?|fanzines?)\b', t_titre, re.I):
                                is_allowed_collector = True

                        if not is_allowed_collector:
                            item.pop('_prefetched_html', None)
                            log(f"🚫 [Smart-Inspector] Article Magic Fans exclu ({r_sp}) : '{t_titre}'")
                            smart_inspection_queue.task_done()
                            continue
                    is_c_gd, c_grp_d = is_conflicting_supporter_group(desc)
                    if is_c_gd:
                        item.pop('_prefetched_html', None)
                        log(f"🚫 [Smart-Inspector] Article Magic Fans exclu (Groupe adverse en description : {c_grp_d}) : '{t_titre}'")
                        smart_inspection_queue.task_done()
                        continue
                    has_mf_desc, mf_phrase_d = is_magic_fans_collector_match(desc)
                    p_val = parse_price(t_prix)
                    is_asse_j = is_asse_jersey_match(t_titre) or is_asse_jersey_match(desc)
                    if has_mf_desc and (p_val is None or p_val <= 80.0):
                        log(f"🎯 MATCH COLLECTOR MAGIC FANS ('{mf_phrase_d}' dans la description) : '{t_titre}' ({t_prix})")
                        send_discord_alert(None, item, bypass_jersey_filters=True)
                    elif has_mf_desc and is_asse_j and (p_val is None or p_val <= 350.0):
                        log(f"🎯 MATCH MAILLOT ASSE (détecté via scan Magic Fans) : '{t_titre}' ({t_prix})")
                        send_discord_alert(None, item, bypass_jersey_filters=False)
                    elif has_mf_desc and p_val is not None and p_val > 80.0:
                        item.pop('_prefetched_html', None)
                        log(f"🚫 [Smart-Inspector] Magic Fans non-maillot exclu car prix ({p_val}€) > 80€ : '{t_titre}'")
                    else:
                        item.pop('_prefetched_html', None)
                        log(f"🚫 [Smart-Inspector] Article Magic Fans ignoré (Pas de mention Magic Fans / MF91) : '{t_titre}'")
                    smart_inspection_queue.task_done()
                    time.sleep(1.5)
                    continue

                # Vérifier exclusion produit dans la description
                is_excl_d, reason_d = is_excluded_product(t_titre, desc, t_prix)
                if is_excl_d:
                    item.pop('_prefetched_html', None)
                    log(f"🚫 [Smart-Inspector] Article #{item_id} exclu description ({reason_d}) : '{t_titre}'")
                    smart_inspection_queue.task_done()
                    continue

                is_bad_brand, bad_brand_reason = is_incompatible_kit_brand(item.get('brand'), t_titre)
                if is_bad_brand:
                    item.pop('_prefetched_html', None)
                    log(f"🚫 [Smart-Inspector] Article #{item_id} exclu ({bad_brand_reason}) : '{t_titre}' (Marque: {item.get('brand')})")
                    smart_inspection_queue.task_done()
                    continue

                if FILTER_ADULT_ONLY:
                    is_excl_sd, reason_sd = is_excluded_size(item.get('size', 'N/A'), t_titre, desc)
                    if is_excl_sd:
                        item.pop('_prefetched_html', None)
                        log(f"🚫 [Smart-Inspector] Article #{item_id} exclu taille ({reason_sd}) : '{t_titre}'")
                        smart_inspection_queue.task_done()
                        continue

                # Vérifier absence de club rival en description
                is_conf_d, conf_d = is_conflicting_team(desc)
                if is_conf_d:
                    item.pop('_prefetched_html', None)
                    log(f"🚫 [Smart-Inspector] Article #{item_id} exclu club rival ({conf_d}) : '{t_titre}'")
                    smart_inspection_queue.task_done()
                    continue

                # Signal ASSE dans la description (ou combiné titre + description) ?
                has_sig_d, sig_reason_d = is_asse_signal(desc, is_filet=True)
                if has_sig_d:
                    log(f"🎯 MATCH SMART-INSPECTOR #{item_id} ({sig_reason_d} en description) : '{t_titre}' ({t_prix})")
                    send_discord_alert(None, item)
                else:
                    item.pop('_prefetched_html', None)
                    log(f"ℹ️ [Smart-Inspector] Pas de confirmation ASSE en description pour #{item_id} : '{t_titre}'")

            smart_inspection_queue.task_done()
            time.sleep(1.5)  # Temporisation anti-burst pour respecter Vinted
        except Exception as e:
            log(f"⚠️ [Smart-Inspector] Erreur inspection: {e}")
            time.sleep(2)

def process_incoming_items_safe(items, source_label="Flux", is_initial=False):
    """Traite une liste d'articles récupérés de manière thread-safe (filtrage et alertes Discord)"""
    global flux_seen_ids, filet_seen_ids, alerted_ids, shared_last_seen_id, initialized_sources
    with state_lock:
        is_filet = "Filet" in source_label

        # Gestion intelligente de l'initialisation :
        # Au premier passage, on n'absorbe que le véritable ancien historique (> 1h ou ID <= shared_last_seen_id).
        # Tout article récent (publié pendant un redémarrage court) ou frais dans le Filet est conservé pour être analysé !
        if source_label not in initialized_sources or is_initial:
            initialized_sources.add(source_label)
            count_absorbed = 0
            items_to_keep = []

            for item in items:
                try:
                    i_id = int(item['id'])
                except (ValueError, TypeError):
                    continue

                # Déjà alerté : jamais de doublon
                if i_id in alerted_ids:
                    continue

                is_fresh_item = False
                if shared_last_seen_id > 0:
                    diff = i_id - shared_last_seen_id
                    # 1. Annonce publiée pendant le redémarrage (ID supérieur au dernier ID vu)
                    if diff > 0:
                        is_fresh_item = True
                    # 2. Pour le Filet : annonce dans les recherches mots-clés jamais vue dans le cache.
                    # Vinted traite ~1.2M annonces/h en Europe. Une annonce modérée ou retardée
                    # de quelques heures peut avoir un ID décalé de plusieurs millions.
                    # On conserve toute annonce non vue dans les dernières ~12h (~15M IDs).
                    elif is_filet and diff > -15000000 and i_id not in filet_seen_ids:
                        is_fresh_item = True

                if is_fresh_item:
                    items_to_keep.append(item)
                else:
                    if is_filet:
                        if i_id not in filet_seen_ids:
                            filet_seen_ids.add(i_id)
                            count_absorbed += 1
                    else:
                        if i_id not in flux_seen_ids:
                            flux_seen_ids.add(i_id)
                            count_absorbed += 1

            if count_absorbed > 0:
                if is_filet:
                    save_filet_seen_ids_cache(filet_seen_ids)
                else:
                    save_seen_ids_cache(flux_seen_ids)
                log(f"📥 [{source_label}] {count_absorbed} annonce(s) d'historique absorbée(s) à l'initialisation.")

            # S'il y a des annonces fraîches à traiter, on remplace items par items_to_keep
            # Sinon, on s'arrête là pour ce cycle d'initialisation
            if not items_to_keep:
                return
            items = items_to_keep

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
                # Filet de sécurité : toute nouvelle annonce arrivant sur la 1ère page non vue est traitée
                if item_id not in filet_seen_ids:
                    new_found.append(item)
                    filet_seen_ids.add(item_id)
            else:
                # Flux général : toute nouvelle annonce non vue est traitée
                if item_id not in flux_seen_ids:
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

            # Cas spécial prioritaire : Recherche Collector / Accessoires 'Magic Fans' (toutes les 45-60s ou via flux)
            is_magic_fans_scan = "Magic Fans" in source_label or "MF91" in source_label or "MF 91" in source_label
            if is_magic_fans_scan:
                # Éliminer dès le titre tout club concurrent ou groupe adverse
                is_conf_t, conf_t = is_conflicting_team(t_titre)
                if is_conf_t:
                    log(f"🚫 Article Magic Fans ignoré dès le titre (Club concurrent : {conf_t}) : '{t_titre}'")
                    continue
                is_conf_g, conf_g = is_conflicting_supporter_group(t_titre)
                if is_conf_g:
                    log(f"🚫 Article Magic Fans ignoré dès le titre (Groupe adverse : {conf_g}) : '{t_titre}'")
                    continue

            has_mf_title, mf_phrase_t = is_magic_fans_collector_match(t_titre)
            if has_mf_title:
                p_val = parse_price(t_prix)
                if p_val is None or p_val <= 80.0:
                    log(f"🎯 MATCH COLLECTOR MAGIC FANS ('{mf_phrase_t}' dans le titre) : '{t_titre}' ({t_prix})")
                    send_discord_alert(None, item, bypass_jersey_filters=True)
                    continue
                else:
                    log(f"ℹ️ Article Magic Fans > 80€ ({p_val}€) : redirection vers filtres maillots standards : '{t_titre}'")

            if is_magic_fans_scan:
                # Pré-filtrage rapide des articles manifestement hors-sujet ou autocollants
                if MAGIC_FANS_NOISE_PATTERN.search(t_titre):
                    log(f"🚫 Article Magic Fans ignoré dès le titre (Hors-sujet) : '{t_titre}'")
                    continue
                if MAGIC_FANS_STICKER_PATTERN.search(t_titre):
                    log(f"🚫 Article Magic Fans ignoré dès le titre (Autocollant / Sticker) : '{t_titre}'")
                    continue
                p_val = parse_price(t_prix)
                if p_val is not None and p_val > 80.0:
                    log(f"🚫 Article Magic Fans ignoré dès la liste car prix ({p_val}€) > 80€ : '{t_titre}'")
                    continue
                try:
                    smart_inspection_queue.put_nowait((item, "Magic Fans Collector"))
                    log(f"📥 [Magic Fans] Candidat en file d'inspection asynchrone : '{t_titre}'")
                except queue.Full:
                    pass
                continue

            # 1. Filtrage des produits indésirables (Mug, Panini, Prix > 350€, Vestes)
            is_excl, reason = is_excluded_product(t_titre, '', t_prix)
            if is_excl:
                log(f"🚫 Article ignoré dès la liste ({reason}) : '{t_titre}' ({t_prix})")
                continue

            if item.get('brand'):
                is_bad_brand, bad_brand_reason = is_incompatible_kit_brand(item.get('brand'), t_titre)
                if is_bad_brand:
                    log(f"🚫 Article ignoré dès la liste ({bad_brand_reason}) : '{t_titre}' (Marque: {item.get('brand')})")
                    continue

            # 2. Filtrage des tailles enfants et XS/S
            if FILTER_ADULT_ONLY and item.get('size') and item.get('size') != 'N/A':
                is_excl, reason = is_excluded_size(item['size'], item.get('title', ''))
                if is_excl:
                    log(f"🚫 Article ignoré dès la liste ({reason}) : '{item.get('title')}' (Taille: {item['size']})")
                    continue

            # 3. Correspondance ASSE
            matched = False
            if is_asse_jersey_match(t_titre):
                matched = True
                log(f"🎯 MATCH {source_label} : '{t_titre}' ({t_prix})")
            elif not is_filet:
                # Flux Direct Foot : Détection aussi par Joueur ASSE / Sponsor historique / Chaudron
                # si le titre contient un mot de maillot ou t-shirt et aucune équipe concurrente
                has_shirt_kw = bool(re.search(
                    r'\b(maillots?|jerseys?|trikots?|camisetas?|maglias?|tenues?|ensembles?|t-?shirts?|tee[- ]?shirts?|shirts?|hauts?)\b',
                    t_titre, re.IGNORECASE
                ))
                if has_shirt_kw:
                    is_conf_f, conf_team_f = is_conflicting_team(t_titre)
                    if not is_conf_f:
                        has_sig_f, sig_reason_f = is_asse_signal(t_titre, is_filet=False)
                        if has_sig_f:
                            matched = True
                            log(f"🎯 MATCH {source_label} ({sig_reason_f}) : '{t_titre}' ({t_prix})")

                # Si non matché directement dans le titre, est-ce un candidat pour inspection description en arrière-plan ?
                if not matched and not is_conflicting_team(t_titre)[0]:
                    is_cand, reason_cand = is_flux_smart_candidate(t_titre)
                    if is_cand:
                        try:
                            smart_inspection_queue.put_nowait((item, reason_cand))
                            log(f"📥 [Flux Direct Foot] Candidat en file d'inspection ({reason_cand}) : '{t_titre}'")
                        except queue.Full:
                            pass
            elif is_filet:
                # Filet de sécurité ('Maillot Asse') : Uniquement ici, utilisation des bases Joueurs, Sponsors et Vert
                is_conf, conf_team = is_conflicting_team(t_titre)
                if is_conf:
                    log(f"🚫 Article Filet ignoré (Équipe concurrente dans le titre : {conf_team}) : '{t_titre}'")
                    continue

                # Test du signal dans le titre (Mention ASSE, Joueur, Sponsor ou Mot-clé club)
                has_sig_t, sig_reason_t = is_asse_signal(t_titre, is_filet=True)
                if has_sig_t:
                    matched = True
                    log(f"🎯 MATCH {source_label} ({sig_reason_t}) : '{t_titre}' ({t_prix})")
                else:
                    # Si pas de signal direct dans le titre, test dans la description
                    desc = fetch_item_description(item_url, item=item)
                    if desc:
                        is_excl_d, reason_d = is_excluded_product(t_titre, desc, t_prix)
                        if is_excl_d:
                            log(f"🚫 Article ignoré après vérification description ({reason_d}) : '{t_titre}'")
                            continue
                        if FILTER_ADULT_ONLY:
                            is_excl_sd, reason_sd = is_excluded_size(item.get('size', 'N/A'), t_titre, desc)
                            if is_excl_sd:
                                log(f"🚫 Article ignoré après vérification taille description ({reason_sd}) : '{t_titre}'")
                                continue
                        is_conf_d, conf_d = is_conflicting_team(desc)
                        if is_conf_d:
                            log(f"🚫 Article Filet ignoré (Équipe concurrente dans la description : {conf_d}) : '{t_titre}'")
                            continue
                        has_sig_d, sig_reason_d = is_asse_signal(desc, is_filet=True)
                        if has_sig_d:
                            matched = True
                            log(f"🎯 MATCH {source_label} ({sig_reason_d} dans description) : '{t_titre}' ({t_prix})")
                        else:
                            log(f"🚫 Article Filet ignoré (Aucun signal ASSE/Joueur/Sponsor) : '{t_titre}'")
                            continue
                    else:
                        log(f"🚫 Article Filet ignoré (Titre sans signal ASSE et description inaccessible) : '{t_titre}'")
                        continue

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
    
    # Filet de Sécurité Turbo centré sur ASSE, Saint-Étienne et St-Étienne (catalogue football 3267 anti-pollution)
    SAFETY_QUERIES = [
        ("Maillot Asse", get_search_url("Maillot Asse")),
        ("Maillot Saint Etienne", get_search_url("Maillot Saint Etienne") + "&catalog_ids[]=3267"),
        ("Maillot St Etienne", get_search_url("Maillot St Etienne") + "&catalog_ids[]=3267"),
    ]
    # Rotation Accessoires & Collectors Magic Fans (< 80€)
    MAGIC_FANS_QUERIES = [
        ("Magic Fans", get_search_url("Magic Fans") + "&price_to=80"),
        ("MF91", get_search_url("MF91") + "&price_to=80"),
        ("MF 91", get_search_url("MF 91") + "&price_to=80"),
        ("Echarpe Magic Fans", get_search_url("echarpe Magic Fans") + "&price_to=80"),
        ("SNK Magic Fans", get_search_url("SNK Magic Fans") + "&price_to=80"),
    ]

    log("🚀 [Vinted] Démarrage du Moteur Turbo-Sniper (Priorité 90% Foot Temps Réel + Timeout Ultra-Court 4.5s)")
    log("⚡ [Vinted] 9 Scans Foot Direct pour 1 Scan Filet Sécurité + Cycle Collector 'Magic Fans'")
    log("📸 [Vinted] Support jusqu'à 20 photos HD avec notifications silencieuses")

    safety_index = 0
    magic_fans_index = 0
    is_initial_scan = True
    last_magic_fans_scan = 0

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
                page.set_default_timeout(4500)

                session_start_time = time.time()
                cycle_count = 0
                consecutive_errors = 0

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

                    # Purge préventive de l'onglet tous les 120 scans (~5 minutes)
                    if cycle_count % 120 == 0:
                        try: page.close()
                        except: pass
                        try:
                            page = context.new_page()
                            page.set_default_timeout(4500)
                        except: pass

                    # Choix de la cible (Priorité 90%+ au Flux Direct Foot, surtout aux heures de pointe 17h-22h) :
                    is_peak_hour = 17 <= paris_now.hour < 22
                    mf_interval = 60 if is_peak_hour else 45
                    if not is_initial_scan and (now - last_magic_fans_scan) >= mf_interval:
                        mf_label, target_url = MAGIC_FANS_QUERIES[magic_fans_index % len(MAGIC_FANS_QUERIES)]
                        magic_fans_index += 1
                        scan_label = f"Filet Collector '{mf_label}'"
                        last_magic_fans_scan = now
                    elif cycle_count % 10 == 0:
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

                        page.goto(target_url, wait_until='commit', timeout=4500)
                        items = extract_items_from_page(page)
                        log(f"⚡ [Vinted] Scan {scan_label} : {len(items)} annonces")
                        update_watchdog_heartbeat()
                        consecutive_errors = 0
                        if items:
                            process_incoming_items_safe(items, scan_label, is_initial=is_initial_scan)
                            if is_initial_scan and cycle_count >= 5:
                                is_initial_scan = False
                    except Exception as e:
                        consecutive_errors += 1
                        err_str = str(e).lower()
                        is_transient = any(k in err_str for k in ["timeout", "interrupted", "err_aborted"])
                        # En cas de micro-latence ou timeout (>4.5s), recyclage propre et immédiat du navigateur
                        # plutôt que de tenter une relance sur un onglet Playwright au socket gelé
                        if is_transient and consecutive_errors < 2:
                            log(f"ℹ️ [Vinted] Micro-latence réseau ({consecutive_errors}/2) sur {scan_label} : recyclage propre immédiat...")
                            break
                        else:
                            log(f"⚠️ [Vinted] Erreur locale ({consecutive_errors} consécutives) : {e}")
                            break
                    finally:
                        if hasattr(signal, "SIGALRM"):
                            signal.alarm(0)

                    # Pause ultra-réactive (0.5s à 0.8s sur le Flux Direct Foot, 1.0s à 1.3s sur le Filet)
                    if scan_label == "Flux Direct Foot":
                        time.sleep(random.uniform(0.5, 0.8))
                    else:
                        time.sleep(random.uniform(1.0, 1.3))

                try: browser.close()
                except: pass
        except Exception as e:
            log(f"🚨 [Vinted] Incident navigateur : {e}. Redémarrage dans 6s...")
            time.sleep(6)

def run_bot():
    try:
        # Lancement du worker d'inspection asynchrone (Queue en tâche de fond)
        inspector_thread = threading.Thread(target=worker_smart_inspection, daemon=True, name="SmartInspector")
        inspector_thread.start()
        log("🚀 [Smart-Inspector] Thread d'inspection asynchrone prêt")

        # Lancement du watchdog de surveillance autonome en tâche de fond
        watchdog_thread = threading.Thread(target=watchdog_thread_worker, daemon=True, name="WatchdogMonitor")
        watchdog_thread.start()
        log("🛡️ [Watchdog] Thread de surveillance autonome actif (détection de gel >90s)")

        worker_turbo_sniper()
    except KeyboardInterrupt:
        log("\n⛔ [Vinted] Arrêt du bot demandé")
    finally:
        log("👋 [Vinted] Bot éteint proprement")

if __name__ == "__main__":
    run_bot()
