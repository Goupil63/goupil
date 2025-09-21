import os
import time
import random
import logging
import requests
import json
from bs4 import BeautifulSoup
from datetime import datetime, timedelta

# ----------------------
# CONFIGURATION
# ----------------------
VINTED_URL = os.getenv("VINTED_URL")
DISCORD_WEBHOOK = os.getenv("DISCORD_WEBHOOK")
SEEN_FILE = "seen.json"

MIN_DELAY = 180   # délai minimum entre 2 scrapes (secondes)
MAX_DELAY = 300   # délai maximum entre 2 scrapes (secondes)
RUN_DURATION = 60 * 60  # durée totale du run (1 heure)

# ----------------------
# LOGGING
# ----------------------
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("vinted-bot")

# ----------------------
# SESSION HTTP
# ----------------------
session = requests.Session()
session.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept-Language": "fr-FR,fr;q=0.9"
})

# ----------------------
# MEMOIRE PERSISTANTE
# ----------------------
def load_seen():
    if os.path.exists(SEEN_FILE):
        with open(SEEN_FILE, "r") as f:
            return set(json.load(f))
    return set()

def save_seen(seen_items):
    with open(SEEN_FILE, "w") as f:
        json.dump(list(seen_items), f)

seen_items = load_seen()

# ----------------------
# DISCORD
# ----------------------
def send_to_discord(title, price, link, img_url=""):
    if not title or not link:
        logger.warning("Titre ou lien vide, notification Discord ignorée")
        return
    data = {
        "embeds": [{
            "title": f"{title} - {price}",
            "url": link,
            "color": 3447003,
            "image": {"url": img_url} if img_url else None
        }]
    }
    try:
        resp = session.post(DISCORD_WEBHOOK, json=data, timeout=10)
        if resp.status_code // 100 != 2:
            logger.warning(f"Discord Webhook renvoyé {resp.status_code}")
    except Exception as e:
        logger.error(f"Erreur en envoyant à Discord : {e}")

# ----------------------
# SCRAPER VINTED
# ----------------------
def fetch_latest_links():
    """Récupère les 20 dernières annonces"""
    try:
        resp = session.get(VINTED_URL, timeout=12)
        if resp.status_code != 200:
            logger.warning(f"Réponse inattendue {resp.status_code}")
            return []
        soup = BeautifulSoup(resp.text, "html.parser")
        container = soup.find("div", class_="feed-grid")
        if not container:
            logger.warning("❌ Container feed-grid non trouvé")
            return []
        items = container.find_all("div", class_="feed-grid__item")
        links = []
        for item in items[:20]:
            link_tag = item.find("a", href=True)
            if not link_tag:
                continue
            link = link_tag['href']
            if not link.startswith("http"):
                link = "https://www.vinted.fr" + link
            links.append(link)
        return links
    except Exception as e:
        logger.error(f"Erreur récupération des derniers liens : {e}")
        return []

def scrape_and_notify():
    try:
        resp = session.get(VINTED_URL, timeout=12)
        if resp.status_code != 200:
            logger.warning(f"Réponse inattendue {resp.status_code}")
            return 0

        soup = BeautifulSoup(resp.text, "html.parser")
        container = soup.find("div", class_="feed-grid")
        if not container:
            logger.warning("❌ Container feed-grid non trouvé")
            return 0

        items = container.find_all("div", class_="feed-grid__item")
        logger.info(f"📦 {len(items)} annonces détectées sur la page")

        new_items_count = 0
        for item in items[:20]:
            link_tag = item.find("a", href=True)
            if not link_tag:
                continue
            link = link_tag['href']
            if not link.startswith("http"):
                link = "https://www.vinted.fr" + link
            if link in seen_items:
                continue
            seen_items.add(link)
            new_items_count += 1

            # Titre
            title_tag = item.find("h3") or item.find("h1") or item.find("h2")
            title = title_tag.get_text(strip=True) if title_tag else "Sans titre"

            # Prix
            price_tag = item.find("div", {"data-testid": "item-price"})
            price = price_tag.get_text(strip=True) if price_tag else "Prix non trouvé"

            # Image
            img_tag = item.find("img")
            img_url = img_tag['src'] if img_tag and img_tag.get('src') else ""

            logger.info(f"📬 Nouvelle annonce : {title} - {price}\n🔗 {link}")
            send_to_discord(title, price, link, img_url)

        save_seen(seen_items)
        return new_items_count

    except Exception as e:
        logger.error(f"Erreur scraping : {e}")
        return 0

# ----------------------
# BOUCLE PRINCIPALE
# ----------------------
if __name__ == "__main__":
    start_time = datetime.now()
    end_time = start_time + timedelta(seconds=RUN_DURATION)
    logger.info("🚀 Bot Vinted Requests démarré")
    logger.info(f"📡 URL Vinted : {VINTED_URL}")

    # Initialisation avec les 20 dernières annonces
    if not seen_items:
        latest_links = fetch_latest_links()
        seen_items.update(latest_links)
        save_seen(seen_items)
        logger.info(f"⚡ Initialisation : {len(latest_links)} dernières annonces mémorisées.")

    while datetime.now() < end_time:
        new_count = scrape_and_notify()
        if new_count == 0:
            logger.info("✅ Aucune nouvelle annonce")
        else:
            logger.info(f"📬 {new_count} nouvelles annonces envoyées")
        delay = random.randint(MIN_DELAY, MAX_DELAY)
        logger.info(f"⏰ Pause aléatoire de {delay} secondes avant le prochain scan")
        time.sleep(delay)

    logger.info("⏹️ Run terminé après 1 heure.")
