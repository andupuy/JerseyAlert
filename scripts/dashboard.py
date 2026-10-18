#!/usr/bin/env python3
import http.server
import socketserver
from socketserver import ThreadingMixIn
import base64
import subprocess
import json
import urllib.parse
import os
import time
import threading
import re

PORT = 80
AUTH_USER = os.environ.get("DASHBOARD_USER", "admin")
AUTH_PASS = os.environ.get("DASHBOARD_PASS", "asse2026")
AUTH_HEADER = "Basic " + base64.b64encode(f"{AUTH_USER}:{AUTH_PASS}".encode()).decode()

ERRORS_LOG_FILE = os.environ.get(
    "ERRORS_LOG_FILE",
    "/root/vinted_errors.log" if os.path.exists("/root") else "vinted_errors.log"
)
RESET_TIMESTAMP_FILE = os.environ.get(
    "RESET_TIMESTAMP_FILE",
    "/root/.last_errors_reset" if os.path.exists("/root") else ".last_errors_reset"
)
BLACKLIST_FILE = os.environ.get(
    "BLACKLIST_FILE",
    "/root/JerseyAlert/blacklisted_sellers.json" if os.path.exists("/root/JerseyAlert") else "blacklisted_sellers.json"
)

# In-memory caches to handle multi-device / multi-client connections seamlessly without CPU overload
cache_lock = threading.Lock()
logs_cache = {
    "timestamp": 0,
    "full": "",
    "errors": "",
    "error_count": 0
}
status_cache = {
    "timestamp": 0,
    "data": {}
}

ERROR_PATTERNS = re.compile(
    r"(\]\s*(?:⚠️|🚨|❌)|[Ww]atchdog:|[Tt]raceback)",
    re.UNICODE
)

IGNORE_PATTERNS = re.compile(
    r"(write EPIPE|emitError|Unhandled 'error'|Emitted 'error'|Socket instance|node:internal|node:events|Node\.js|SyntaxWarning|errno: -32|syscall: 'write'|WriteWrap|processTicksAndRejections|Micro-latence réseau|reprise fluide|Détecté #|Article ignoré|Scan Flux|Scan Filet)",
    re.IGNORECASE
)

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

def get_blacklisted_sellers():
    """Charge la liste des vendeurs bloqués"""
    if os.path.exists(BLACKLIST_FILE):
        try:
            with open(BLACKLIST_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                return sorted(list({normalize_seller_name(s) for s in data if normalize_seller_name(s)}))
        except Exception:
            pass
    return []

def save_blacklisted_sellers(sellers_list):
    """Sauvegarde la liste des vendeurs bloqués"""
    clean_list = sorted(list({normalize_seller_name(s) for s in sellers_list if normalize_seller_name(s)}))
    try:
        os.makedirs(os.path.dirname(os.path.abspath(BLACKLIST_FILE)), exist_ok=True)
        with open(BLACKLIST_FILE, "w", encoding="utf-8") as f:
            json.dump(clean_list, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"Erreur sauvegarde blacklist: {e}")
    return clean_list

class ThreadedTCPServer(ThreadingMixIn, socketserver.TCPServer):
    allow_reuse_address = True
    daemon_threads = True

class DashboardHandler(http.server.BaseHTTPRequestHandler):
    timeout = 10  # Prevent hanging socket connections

    def log_message(self, format, *args):
        # Silence console log spam
        pass

    def check_auth(self):
        auth = self.headers.get("Authorization")
        if auth == AUTH_HEADER:
            return True
        self.send_response(401)
        self.send_header("WWW-Authenticate", 'Basic realm="Vinted Bot Dashboard"')
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(b"<h1>401 Acces non autorise</h1>")
        return False

    def do_GET(self):
        if not self.check_auth():
            return

        parsed = urllib.parse.urlparse(self.path)
        if parsed.path == "/":
            content = self.render_dashboard().encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            self.wfile.write(content)
        elif parsed.path == "/api/status":
            data = self.get_cached_status()
            self.send_json_response(data)
        elif parsed.path == "/api/logs":
            logs_data = self.get_cached_logs()
            content = logs_data["full"].encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            self.wfile.write(content)
        elif parsed.path == "/api/errors":
            logs_data = self.get_cached_logs()
            self.send_json_response({
                "errors": logs_data["errors"],
                "count": logs_data["error_count"]
            })
        elif parsed.path == "/api/blacklist":
            sellers = get_blacklisted_sellers()
            self.send_json_response({
                "sellers": sellers,
                "count": len(sellers)
            })
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        if not self.check_auth():
            return

        parsed = urllib.parse.urlparse(self.path)
        if parsed.path == "/api/restart":
            subprocess.run(["systemctl", "restart", "vinted-bot"], timeout=10)
            self.send_json_response({"success": True, "message": "Bot redémarré avec succès !"})
        elif parsed.path == "/api/stop":
            subprocess.run(["systemctl", "stop", "vinted-bot"], timeout=10)
            self.send_json_response({"success": True, "message": "Bot mis en pause !"})
        elif parsed.path == "/api/start":
            subprocess.run(["systemctl", "start", "vinted-bot"], timeout=10)
            self.send_json_response({"success": True, "message": "Bot démarré !"})
        elif parsed.path == "/api/clear-errors":
            try:
                now_epoch = time.time()
                with open(RESET_TIMESTAMP_FILE, "w") as f:
                    f.write(str(now_epoch))
                now_str = time.strftime("%Y-%m-%d %H:%M:%S")
                with open(ERRORS_LOG_FILE, "w", encoding="utf-8") as f:
                    f.write(f"[{now_str}] 🧹 Historique des erreurs réinitialisé par l'utilisateur.\n")
                with cache_lock:
                    logs_cache["timestamp"] = 0
                self.send_json_response({"success": True, "message": "Historique des erreurs réinitialisé !"})
            except Exception as e:
                self.send_json_response({"success": False, "message": f"Erreur: {e}"})
        elif parsed.path == "/api/blacklist/add":
            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length).decode("utf-8")
            try:
                data = json.loads(body)
            except Exception:
                data = urllib.parse.parse_qs(body)
                data = {k: v[0] for k, v in data.items()}
            seller_raw = data.get("seller", "")
            clean_name = normalize_seller_name(seller_raw)
            if clean_name:
                current = get_blacklisted_sellers()
                if clean_name not in current:
                    current.append(clean_name)
                    save_blacklisted_sellers(current)
                self.send_json_response({
                    "success": True,
                    "message": f"Vendeur '@{clean_name}' bloqué avec succès !",
                    "sellers": sorted(current),
                    "count": len(current)
                })
            else:
                self.send_json_response({"success": False, "message": "Pseudo de vendeur invalide."})
        elif parsed.path == "/api/blacklist/remove":
            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length).decode("utf-8")
            try:
                data = json.loads(body)
            except Exception:
                data = urllib.parse.parse_qs(body)
                data = {k: v[0] for k, v in data.items()}
            seller_raw = data.get("seller", "")
            clean_name = normalize_seller_name(seller_raw)
            if clean_name:
                current = get_blacklisted_sellers()
                if clean_name in current:
                    current.remove(clean_name)
                    save_blacklisted_sellers(current)
                self.send_json_response({
                    "success": True,
                    "message": f"Vendeur '@{clean_name}' débloqué !",
                    "sellers": sorted(current),
                    "count": len(current)
                })
            else:
                self.send_json_response({"success": False, "message": "Pseudo de vendeur invalide."})
        else:
            self.send_response(404)
            self.end_headers()

    def send_json_response(self, data):
        content = json.dumps(data).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)

    def get_cached_status(self):
        global status_cache
        now = time.time()
        with cache_lock:
            if now - status_cache["timestamp"] < 2.0 and status_cache["data"]:
                return status_cache["data"]

        # Re-fetch
        status_data = self.fetch_system_status()
        with cache_lock:
            status_cache["timestamp"] = now
            status_cache["data"] = status_data
        return status_data

    def fetch_system_status(self):
        # Service status
        res = subprocess.run(["systemctl", "is-active", "vinted-bot"], capture_output=True, text=True, timeout=5)
        is_active = res.stdout.strip()

        # RAM & Swap usage
        ram_used = "N/A"
        ram_total = "N/A"
        swap_used = "N/A"
        swap_total = "N/A"
        try:
            free_res = subprocess.run(["free", "-m"], capture_output=True, text=True, timeout=5)
            lines = free_res.stdout.strip().split("\n")
            for line in lines:
                parts = line.split()
                if "Mem:" in parts[0]:
                    ram_total = f"{parts[1]} Mo"
                    ram_used = f"{parts[2]} Mo"
                elif "Swap:" in parts[0]:
                    swap_total = f"{parts[1]} Mo"
                    swap_used = f"{parts[2]} Mo"
        except Exception:
            pass

        # Load average
        load_avg = "N/A"
        try:
            with open("/proc/loadavg", "r") as f:
                load_avg = f.read().split()[:3]
                load_avg = ", ".join(load_avg)
        except Exception:
            pass

        return {
            "status": is_active,
            "ram_used": ram_used,
            "ram_total": ram_total,
            "swap_used": swap_used,
            "swap_total": swap_total,
            "uptime": load_avg
        }

    def get_cached_logs(self):
        global logs_cache
        now = time.time()
        with cache_lock:
            if now - logs_cache["timestamp"] < 2.0 and logs_cache["full"]:
                return logs_cache

        # Re-fetch from journalctl and persistent file
        full_logs, error_logs, error_count = self.fetch_logs_and_errors()
        with cache_lock:
            logs_cache["timestamp"] = now
            logs_cache["full"] = full_logs
            logs_cache["errors"] = error_logs
            logs_cache["error_count"] = error_count
            return logs_cache

    def fetch_logs_and_errors(self):
        try:
            # 1. Fetch live stream
            res = subprocess.run(
                ["journalctl", "-u", "vinted-bot", "-n", "150", "--no-pager"],
                capture_output=True, text=True, timeout=5
            )
            raw_text = res.stdout

            # Read last reset epoch
            last_reset = 0.0
            if os.path.exists(RESET_TIMESTAMP_FILE):
                try:
                    with open(RESET_TIMESTAMP_FILE, "r") as f:
                        last_reset = float(f.read().strip())
                except Exception:
                    pass

            # 2. Sync any unexpected systemd error lines that occurred strictly AFTER the reset
            if last_reset > 0:
                since_arg = f"--since=@{int(last_reset)}"
                sync_res = subprocess.run(
                    ["journalctl", "-u", "vinted-bot", since_arg, "--no-pager"],
                    capture_output=True, text=True, timeout=5
                )
                check_lines = sync_res.stdout.splitlines()
            else:
                check_lines = raw_text.splitlines()

            new_errs = []
            for line in check_lines:
                if ERROR_PATTERNS.search(line) and not IGNORE_PATTERNS.search(line):
                    new_errs.append(line)

            if new_errs and os.path.exists(ERRORS_LOG_FILE):
                try:
                    with open(ERRORS_LOG_FILE, "r", encoding="utf-8", errors="replace") as f:
                        existing_tail = set(f.read().splitlines()[-100:])
                    to_append = [e for e in new_errs if e not in existing_tail]
                    if to_append:
                        with open(ERRORS_LOG_FILE, "a", encoding="utf-8") as f:
                            for e in to_append:
                                f.write(e + "\n")
                except Exception:
                    pass

            # 3. Read full persistent error history
            if os.path.exists(ERRORS_LOG_FILE):
                with open(ERRORS_LOG_FILE, "r", encoding="utf-8", errors="replace") as f:
                    stored_lines = [
                        l.strip() for l in f
                        if l.strip() and not IGNORE_PATTERNS.search(l)
                    ]
            else:
                stored_lines = []

            # Count only actual errors (ignore user reset notification line if alone)
            real_errors = [l for l in stored_lines if "🧹 Historique des erreurs réinitialisé" not in l]
            error_count = len(real_errors)

            if stored_lines:
                error_text = "\n".join(stored_lines)
            else:
                error_text = "✅ Aucun avertissement ni incident enregistré dans l'historique. Tout roule parfaitement !"

            return raw_text, error_text, error_count
        except Exception as e:
            err = f"Erreur lecture logs: {e}"
            return err, err, 0

    def render_dashboard(self):
        return """<!DOCTYPE html>
<html lang="fr">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
    <title>ASSE Bot Dashboard</title>
    <style>
        :root {
            --bg: #090d16;
            --card: #131c2e;
            --card-border: #1e293b;
            --text: #f8fafc;
            --muted: #94a3b8;
            --green: #22c55e;
            --green-glow: rgba(34, 197, 94, 0.15);
            --red: #ef4444;
            --red-glow: rgba(239, 68, 68, 0.15);
            --amber: #f59e0b;
            --blue: #3b82f6;
            --terminal-bg: #030712;
        }
        * { box-sizing: border-box; margin: 0; padding: 0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; }
        body { background: var(--bg); color: var(--text); padding: 14px; min-height: 100vh; }
        .header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 14px; }
        h1 { font-size: 1.25rem; font-weight: 700; display: flex; align-items: center; gap: 8px; }
        .badge { padding: 4px 10px; border-radius: 9999px; font-size: 0.75rem; font-weight: 700; text-transform: uppercase; }
        .badge.active { background: var(--green-glow); color: var(--green); border: 1px solid var(--green); }
        .badge.inactive { background: rgba(239, 68, 68, 0.2); color: var(--red); border: 1px solid var(--red); }
        
        .stats-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; margin-bottom: 12px; }
        .card { background: var(--card); border: 1px solid var(--card-border); border-radius: 12px; padding: 12px; }
        .card-label { font-size: 0.75rem; color: var(--muted); margin-bottom: 4px; }
        .card-value { font-size: 1.05rem; font-weight: 700; color: #fff; }
        
        .actions { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; margin-bottom: 12px; }
        button {
            border: none; padding: 12px; border-radius: 10px; font-size: 0.95rem; font-weight: 600; cursor: pointer;
            transition: all 0.2s; display: flex; align-items: center; justify-content: center; gap: 6px;
        }
        button:active { opacity: 0.7; transform: scale(0.98); }
        .btn-restart { background: #0284c7; color: white; }
        .btn-toggle { background: #1e293b; color: white; border: 1px solid var(--card-border); }

        /* Tabs bar */
        .tab-bar {
            display: flex; gap: 6px; margin-bottom: 8px; background: var(--card); padding: 4px; border-radius: 10px; border: 1px solid var(--card-border);
        }
        .tab-btn {
            flex: 1; padding: 8px 10px; font-size: 0.8rem; font-weight: 600; background: transparent; color: var(--muted);
            border-radius: 8px; border: none; cursor: pointer; display: flex; align-items: center; justify-content: center; gap: 5px;
        }
        .tab-btn.active {
            background: #1e293b; color: #fff; box-shadow: 0 1px 3px rgba(0,0,0,0.3);
        }
        .pill-count {
            padding: 1px 7px; border-radius: 10px; font-size: 0.7rem; font-weight: 700;
        }
        .pill-zero { background: #334155; color: #94a3b8; }
        .pill-warn { background: var(--amber); color: #000; }
        .pill-red { background: var(--red); color: #fff; }

        .terminal-container {
            background: var(--terminal-bg); border: 1px solid var(--card-border); border-radius: 12px; overflow: hidden;
            display: flex; flex-direction: column; height: 56vh; min-height: 340px;
        }
        .terminal-header {
            background: #0d131f; padding: 8px 12px; font-size: 0.75rem; color: var(--muted);
            display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid var(--card-border);
        }
        .terminal-header-right {
            display: flex; align-items: center; gap: 10px;
        }
        .btn-clear {
            background: rgba(239, 68, 68, 0.15); color: #fca5a5; border: 1px solid rgba(239, 68, 68, 0.4);
            padding: 4px 10px; border-radius: 6px; font-size: 0.72rem; font-weight: 600; cursor: pointer;
            transition: all 0.2s; display: none; align-items: center; gap: 4px;
        }
        .btn-clear:hover { background: rgba(239, 68, 68, 0.35); color: #fff; }

        .btn-copy {
            background: rgba(59, 130, 246, 0.15); color: #93c5fd; border: 1px solid rgba(59, 130, 246, 0.4);
            padding: 4px 10px; border-radius: 6px; font-size: 0.72rem; font-weight: 600; cursor: pointer;
            transition: all 0.2s; display: inline-flex; align-items: center; gap: 4px;
        }
        .btn-copy:hover { background: rgba(59, 130, 246, 0.35); color: #fff; }

        .terminal-logs {
            padding: 10px; font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
            font-size: 0.73rem; line-height: 1.45; color: #10b981; overflow-y: auto; flex: 1; white-space: pre-wrap; word-break: break-all;
        }
        .terminal-logs.errors-view {
            color: #fbbf24;
        }

        /* Blacklist View */
        .blacklist-view {
            background: var(--card); border: 1px solid var(--card-border); border-radius: 12px; padding: 14px;
            display: none; flex-direction: column; height: 56vh; min-height: 340px;
        }
        .form-row {
            display: flex; gap: 8px; margin-bottom: 14px;
        }
        .input-text {
            flex: 1; padding: 10px 14px; border-radius: 8px; border: 1px solid var(--card-border);
            background: #090d16; color: #fff; font-size: 0.85rem; outline: none;
        }
        .input-text:focus { border-color: var(--blue); }
        .btn-add {
            background: #dc2626; color: white; padding: 10px 16px; border-radius: 8px; font-weight: 700;
            font-size: 0.85rem; cursor: pointer; border: none; white-space: nowrap;
        }
        .sellers-container {
            flex: 1; overflow-y: auto; display: flex; flex-direction: column; gap: 8px; padding-right: 4px;
        }
        .seller-item {
            display: flex; justify-content: space-between; align-items: center; background: #090d16;
            border: 1px solid var(--card-border); padding: 10px 14px; border-radius: 8px;
        }
        .seller-name {
            font-weight: 600; font-size: 0.88rem; display: flex; align-items: center; gap: 8px; color: #f8fafc;
        }
        .btn-unblock {
            background: rgba(239, 68, 68, 0.15); color: #fca5a5; border: 1px solid rgba(239, 68, 68, 0.4);
            padding: 5px 12px; border-radius: 6px; font-size: 0.75rem; font-weight: 600; cursor: pointer;
        }
        .btn-unblock:hover { background: rgba(239, 68, 68, 0.35); color: #fff; }
        .empty-sellers {
            text-align: center; color: var(--muted); padding: 40px 10px; font-size: 0.85rem; line-height: 1.6;
        }
        
        #toast {
            position: fixed; bottom: 20px; left: 50%; transform: translateX(-50%);
            background: var(--green); color: #000; font-weight: 700; font-size: 0.85rem;
            padding: 8px 16px; border-radius: 9999px; opacity: 0; transition: opacity 0.3s;
            pointer-events: none; z-index: 100;
        }
    </style>
</head>
<body>
    <div class="header">
        <h1>🟢 Vinted ASSE Bot</h1>
        <span id="botBadge" class="badge active">En ligne</span>
    </div>

    <div class="stats-grid">
        <div class="card">
            <div class="card-label">Mémoire RAM</div>
            <div id="ramStat" class="card-value">...</div>
        </div>
        <div class="card">
            <div class="card-label">Mémoire Swap</div>
            <div id="swapStat" class="card-value">...</div>
        </div>
    </div>

    <div class="actions">
        <button class="btn-restart" onclick="restartBot()">🔄 Redémarrer</button>
        <button id="toggleBtn" class="btn-toggle" onclick="toggleBot()">🛑 Arrêter</button>
    </div>

    <!-- Tabs selector -->
    <div class="tab-bar">
        <button id="tabAll" class="tab-btn active" onclick="switchTab('all')">
            📡 Flux complet
        </button>
        <button id="tabErrors" class="tab-btn" onclick="switchTab('errors')">
            ⚠️ Erreurs <span id="errorBadge" class="pill-count pill-zero">0</span>
        </button>
        <button id="tabBlacklist" class="tab-btn" onclick="switchTab('blacklist')">
            🚫 Vendeurs Bloqués <span id="blacklistBadge" class="pill-count pill-zero">0</span>
        </button>
    </div>

    <!-- Terminal Container (Tabs All & Errors) -->
    <div id="terminalContainer" class="terminal-container">
        <div class="terminal-header">
            <span id="terminalTitle">📡 Flux de logs complet (Temps réel)</span>
            <div class="terminal-header-right">
                <button id="btnCopyLogs" class="btn-copy" onclick="copyCurrentLogs()" title="Copier le texte sélectionné ou l'intégralité du journal">
                    📋 Copier
                </button>
                <button id="btnClearErrors" class="btn-clear" onclick="clearErrorsHistory()">
                    🧹 Vider l'historique
                </button>
                <span id="lastUpdate">Màj ...</span>
            </div>
        </div>
        <div id="logsBox" class="terminal-logs">Chargement des logs...</div>
    </div>

    <!-- Blacklist Container (Tab Blacklist) -->
    <div id="blacklistContainer" class="blacklist-view">
        <form class="form-row" onsubmit="addSeller(event)">
            <input type="text" id="sellerInput" class="input-text" placeholder="Pseudo Vinted (ex: jean_dupont ou @jean_dupont ou URL profil)" required>
            <button type="submit" class="btn-add">➕ Bloquer</button>
        </form>

        <div id="sellersList" class="sellers-container">
            <div class="empty-sellers">Chargement des vendeurs bloqués...</div>
        </div>
    </div>

    <div id="toast">Message</div>

    <script>
        let currentStatus = "active";
        let activeTab = "all";
        let cachedFullLogs = "";
        let cachedErrorLogs = "";
        let cachedSellers = [];
        let isUserInteracting = false;

        function hasUserSelection() {
            const sel = window.getSelection();
            if (!sel || sel.isCollapsed) return false;
            const box = document.getElementById("logsBox");
            return box && box.contains(sel.anchorNode);
        }

        window.addEventListener("DOMContentLoaded", () => {
            const box = document.getElementById("logsBox");
            if (box) {
                box.addEventListener("mousedown", () => { isUserInteracting = true; });
            }
            window.addEventListener("mouseup", () => {
                setTimeout(() => {
                    isUserInteracting = hasUserSelection();
                }, 300);
            });
            document.addEventListener("selectionchange", () => {
                isUserInteracting = hasUserSelection();
            });
        });

        function showToast(msg, bg="#22c55e") {
            const t = document.getElementById("toast");
            t.innerText = msg;
            t.style.background = bg;
            t.style.opacity = "1";
            setTimeout(() => { t.style.opacity = "0"; }, 2500);
        }

        async function copyCurrentLogs() {
            const sel = window.getSelection();
            let textToCopy = "";
            if (sel && !sel.isCollapsed && sel.toString().trim().length > 0) {
                textToCopy = sel.toString();
            } else {
                const box = document.getElementById("logsBox");
                textToCopy = box ? box.innerText : "";
            }
            if (!textToCopy) {
                showToast("Rien à copier", "#f59e0b");
                return;
            }
            try {
                await navigator.clipboard.writeText(textToCopy);
                showToast("📋 Copié dans le presse-papier !");
            } catch(e) {
                const ta = document.createElement("textarea");
                ta.value = textToCopy;
                document.body.appendChild(ta);
                ta.select();
                document.execCommand("copy");
                document.body.removeChild(ta);
                showToast("📋 Copié dans le presse-papier !");
            }
        }

        function switchTab(tab) {
            activeTab = tab;
            const tabAll = document.getElementById("tabAll");
            const tabErrors = document.getElementById("tabErrors");
            const tabBlacklist = document.getElementById("tabBlacklist");
            const termCont = document.getElementById("terminalContainer");
            const blackCont = document.getElementById("blacklistContainer");
            const box = document.getElementById("logsBox");
            const title = document.getElementById("terminalTitle");
            const btnClear = document.getElementById("btnClearErrors");

            tabAll.className = "tab-btn" + (tab === "all" ? " active" : "");
            tabErrors.className = "tab-btn" + (tab === "errors" ? " active" : "");
            tabBlacklist.className = "tab-btn" + (tab === "blacklist" ? " active" : "");

            if (tab === "blacklist") {
                termCont.style.display = "none";
                blackCont.style.display = "flex";
                fetchBlacklist();
            } else {
                termCont.style.display = "flex";
                blackCont.style.display = "none";

                if (tab === "all") {
                    box.className = "terminal-logs";
                    box.innerText = cachedFullLogs || "Chargement du flux complet...";
                    title.innerText = "📡 Flux de logs complet (Temps réel)";
                    btnClear.style.display = "none";
                } else {
                    box.className = "terminal-logs errors-view";
                    box.innerText = cachedErrorLogs || "Chargement de l'historique...";
                    title.innerText = "⚠️ Historique persistant des erreurs et alertes";
                    btnClear.style.display = "inline-flex";
                }
                box.scrollTop = box.scrollHeight;
            }
        }

        async function updateStatus() {
            try {
                const res = await fetch("/api/status");
                const data = await res.json();
                currentStatus = data.status;
                const badge = document.getElementById("botBadge");
                const toggle = document.getElementById("toggleBtn");
                if (data.status === "active") {
                    badge.innerText = "En ligne";
                    badge.className = "badge active";
                    toggle.innerText = "🛑 Arrêter";
                } else {
                    badge.innerText = "Arrêté";
                    badge.className = "badge inactive";
                    toggle.innerText = "▶️ Démarrer";
                }
                document.getElementById("ramStat").innerText = `${data.ram_used} / ${data.ram_total}`;
                document.getElementById("swapStat").innerText = `${data.swap_used} / ${data.swap_total}`;
            } catch(e) {}
        }

        async function fetchLogs() {
            try {
                const res = await fetch("/api/logs");
                const text = await res.text();
                cachedFullLogs = text;
                
                if (activeTab === "all") {
                    const box = document.getElementById("logsBox");
                    if (!hasUserSelection() && !isUserInteracting) {
                        if (box.innerText !== text) {
                            const wasBottom = box.scrollHeight - box.clientHeight <= box.scrollTop + 60;
                            box.innerText = text;
                            if (wasBottom) {
                                box.scrollTop = box.scrollHeight;
                            }
                        }
                    }
                }
                const now = new Date();
                document.getElementById("lastUpdate").innerText = now.toLocaleTimeString();
            } catch(e) {}
        }

        async function fetchErrors() {
            try {
                const res = await fetch("/api/errors");
                const data = await res.json();
                cachedErrorLogs = data.errors;
                
                const errBadge = document.getElementById("errorBadge");
                if (data.count > 0) {
                    errBadge.innerText = data.count;
                    errBadge.className = "pill-count pill-warn";
                } else {
                    errBadge.innerText = "0";
                    errBadge.className = "pill-count pill-zero";
                }

                if (activeTab === "errors") {
                    const box = document.getElementById("logsBox");
                    if (!hasUserSelection() && !isUserInteracting) {
                        if (box.innerText !== data.errors) {
                            const wasBottom = box.scrollHeight - box.clientHeight <= box.scrollTop + 60;
                            box.innerText = data.errors;
                            if (wasBottom) {
                                box.scrollTop = box.scrollHeight;
                            }
                        }
                    }
                }
            } catch(e) {}
        }

        async function fetchBlacklist() {
            try {
                const res = await fetch("/api/blacklist");
                const data = await res.json();
                cachedSellers = data.sellers || [];
                
                const badge = document.getElementById("blacklistBadge");
                badge.innerText = data.count || 0;
                badge.className = "pill-count " + (data.count > 0 ? "pill-red" : "pill-zero");

                renderSellersList(cachedSellers);
            } catch(e) {}
        }

        function renderSellersList(sellers) {
            const list = document.getElementById("sellersList");
            if (!sellers || sellers.length === 0) {
                list.innerHTML = `
                    <div class="empty-sellers">
                        ✅ Aucun vendeur bloqué pour le moment.<br>
                        Saisissez un pseudo Vinted ci-dessus pour bloquer immédiatement ses annonces.
                    </div>`;
                return;
            }

            let html = "";
            for (const s of sellers) {
                html += `
                    <div class="seller-item">
                        <span class="seller-name">👤 @${escapeHtml(s)}</span>
                        <button class="btn-unblock" onclick="removeSeller('${escapeHtml(s)}')">
                            🗑️ Débloquer
                        </button>
                    </div>`;
            }
            list.innerHTML = html;
        }

        function escapeHtml(text) {
            return String(text).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;").replace(/'/g, "&#039;");
        }

        async function addSeller(e) {
            e.preventDefault();
            const input = document.getElementById("sellerInput");
            const seller = input.value.trim();
            if (!seller) return;

            showToast("Ajout en cours...", "#3b82f6");
            try {
                const res = await fetch("/api/blacklist/add", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ seller: seller })
                });
                const data = await res.json();
                if (data.success) {
                    showToast(data.message);
                    input.value = "";
                    fetchBlacklist();
                } else {
                    showToast(data.message || "Erreur", "#ef4444");
                }
            } catch(err) {
                showToast("Erreur communication serveur", "#ef4444");
            }
        }

        async function removeSeller(seller) {
            if (!confirm(`Voulez-vous vraiment débloquer le vendeur @${seller} ?`)) return;
            showToast("Déblocage en cours...", "#f59e0b");
            try {
                const res = await fetch("/api/blacklist/remove", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ seller: seller })
                });
                const data = await res.json();
                if (data.success) {
                    showToast(data.message);
                    fetchBlacklist();
                } else {
                    showToast(data.message || "Erreur", "#ef4444");
                }
            } catch(err) {
                showToast("Erreur communication serveur", "#ef4444");
            }
        }

        async function refreshAll() {
            if (document.hidden) return;
            if (activeTab === "blacklist") {
                await fetchBlacklist();
            } else {
                await Promise.all([fetchLogs(), fetchErrors()]);
            }
        }

        async function clearErrorsHistory() {
            if (!confirm("Voulez-vous vraiment effacer l'historique persistant des erreurs et alertes ?")) return;
            showToast("Réinitialisation...", "#f59e0b");
            try {
                const res = await fetch("/api/clear-errors", { method: "POST" });
                const data = await res.json();
                showToast(data.message || "Historique réinitialisé !");
                await fetchErrors();
            } catch(e) {
                showToast("Erreur lors de la réinitialisation", "#ef4444");
            }
        }

        async function restartBot() {
            showToast("Redémarrage en cours...", "#0284c7");
            await fetch("/api/restart", { method: "POST" });
            setTimeout(() => {
                showToast("Bot redémarré avec succès !");
                updateStatus();
                refreshAll();
            }, 1500);
        }

        async function toggleBot() {
            if (currentStatus === "active") {
                showToast("Arrêt en cours...", "#ef4444");
                await fetch("/api/stop", { method: "POST" });
            } else {
                showToast("Démarrage en cours...", "#22c55e");
                await fetch("/api/start", { method: "POST" });
            }
            setTimeout(() => {
                updateStatus();
                refreshAll();
            }, 1000);
        }

        // Periodic updates with smart intervals
        setInterval(refreshAll, 3000);
        setInterval(() => {
            if (!document.hidden) {
                updateStatus();
                fetchBlacklist();
            }
        }, 5000);

        // Immediate run on load
        updateStatus();
        refreshAll();
        fetchBlacklist();
    </script>
</body>
</html>
"""

if __name__ == "__main__":
    with ThreadedTCPServer(("", PORT), DashboardHandler) as httpd:
        print(f"Dashboard running on port {PORT}")
        httpd.serve_forever()
