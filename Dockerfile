FROM mcr.microsoft.com/playwright/python:v1.41.0-jammy

WORKDIR /app

# Copie des fichiers
COPY requirements.txt .
COPY vinted_bot_oracle.py main.py

# Installation des dépendances Python supplémentaires
RUN pip install --no-cache-dir -r requirements.txt

# Commande de démarrage
CMD ["python3", "main.py"]
# Force Update Sun Sep 27 00:48:00 CEST 2026 (ADD ADULT-ONLY SIZE FILTER: NO KIDS, NO S/XS) 🛡️🚀
