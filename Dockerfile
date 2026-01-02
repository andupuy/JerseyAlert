FROM mcr.microsoft.com/playwright/python:v1.41.0-jammy

WORKDIR /app

# Copie des fichiers
COPY requirements.txt .
COPY vinted_bot_oracle.py main.py

# Installation des dépendances Python supplémentaires
RUN pip install --no-cache-dir -r requirements.txt

# Commande de démarrage
CMD ["python3", "main.py"]
# Force Update Fri Jan 02 19:44:00 CET 2026 (V10.0 WATCH OPTIMIZED) ⌚🔔🚀
