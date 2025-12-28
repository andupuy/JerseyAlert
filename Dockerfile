FROM python:3.9-slim

# Installation des dépendances système pour Playwright
RUN apt-get update && apt-get install -y \
    wget \
    gnupg \
    && rm -rf /var/lib/apt/lists/*

# Copie des fichiers
WORKDIR /app
COPY requirements_oracle.txt requirements.txt
COPY vinted_bot_oracle.py main.py

# Installation des dépendances Python
RUN pip install --no-cache-dir -r requirements.txt

# Installation des navigateurs Playwright
RUN playwright install chromium
RUN playwright install-deps chromium

# Commande de démarrage
CMD ["python", "main.py"]
