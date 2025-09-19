import os
import time
import random
import logging
import json
import requests
from bs4 import BeautifulSoup

# ----------------------
# 1. CONFIGURATION
# ----------------------
VINTED_URL = os.getenv("VINTED_URL")  # ex: "https://www.vinted.fr/catalog?search_text=sac&order=newest_first"
DISCORD_WEBHOOK = os.getenv("DISCORD_WEBHOOK")
SEEN_FILE = "seen.json"

if not VINTED_URL:
    raise SystemExit("⚠️ VINTED_URL non configuré dans les Secrets.")
if not DISCORD_WEBHOOK:
    raise SystemExit("⚠️ DISCORD_WEBHOOK non configuré dans les Secrets.")

MIN_INTERVAL = 180  # 3 minutes
MAX_JITTER = 120    # jusqu'à 2 minutes aléatoires

# ----------------------
# 2. LOGGING
# ----------------------
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("vinted-bot")

# ----------------------
# 3. MEMOIRE PERSISTANTE
# ----------------------
if os.path.exists(SEEN_FILE):
    with open(SEEN_FILE, "r") as f:
        seen_items = set(json.load(f))
else:
    seen_items = set()

def save_seen():
    with open(SEEN_FILE, "w") as f:
        json.dump(list(seen_items), f)

# ----------------------
# 4. SESSION HTTP
# ----------------------
session = requests.Session()
session.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept-Language": "fr-FR,fr;q=0.9"
})

# ----------------------
# 5. DISCORD
# ----------------------
def send_to_discord(title, price, link, img_url=""):
    data = {
        "embeds": [{
            "title": f"{title} - {price}",
            "url": link,
            "image": {"url": img_url} if img_url else None,
            "color": 3447003
        }]
    }
    # Supprime la clé "image" si img_url est vide
    if not img_url:
        data["embeds"][0].pop("image")
    try:
        resp = session.post(DISCORD_WEBHOOK, json=data, timeout=10)
        if resp.status_code // 100 != 2:
            logger.warning(f"Discord Webhook renvoyé {resp.status_code}")
    except Exception as e:
        logger.error(f"Erreur en envoyant à Discord : {e}")

# ----------------------
# 6. SCRAPER VINTED
# ----------------------
def check_vinted():
    try:
        resp = session.get(VINTED_URL, timeout=12)
        if resp.status_code != 200:
            logger.warning(f"Réponse inattendue {resp.status_code}")
            return

        soup = BeautifulSoup(resp.text, "html.parser")
        container = soup.find("div", class_="feed-grid")
        if not container:
            logger.warning("❌ Container feed-grid non trouvé")
            return

        items = container.find_all("div", class_="feed-grid__item")
        logger.info(f"📦 {len(items)} annonces détectées sur la page")

        new_items_count = 0
        for item in items:
            try:
                # Lien
                link_tag = item.find("a", href=True)
                if not link_tag:
                    continue
                link = link_tag['href']
                if not link.startswith("http"):
                    link = "https://www.vinted.fr" + link

                # Ignorer les annonces déjà vues
                if link in seen_items:
                    continue
                seen_items.add(link)
                new_items_count += 1

                # Titre
                title_tag = item.find("h3") or item.find("h2") or item.find("h1")
                title = title_tag.get_text(strip=True) if title_tag else "Titre non trouvé"

                # Prix
                price_tag = (
                    item.find("div", {"data-testid": "item-price"}) or
                    item.find("span", class_="web_ui__Text__text web_ui__Text__subtitle web_ui__Text__left") or
                    item.find("p")
                )
                price = price_tag.get_text(strip=True) if price_tag else "Prix non trouvé"

                # Image
                img_tag = item.find("img")
                img_url = img_tag.get("src") or img_tag.get("data-src") if img_tag else ""

                logger.info(f"📬 Nouvelle annonce : {title} - {price}\n🔗 {link}")
                send_to_discord(title, price, link, img_url)

            except Exception as e:
                logger.error(f"Erreur traitement annonce : {e}")

        if new_items_count == 0:
            logger.info("✅ Aucune nouvelle annonce")
        else:
            logger.info(f"📬 {new_items_count} nouvelles annonces envoyées")
        save_seen()

    except Exception as e:
        logger.error(f"Erreur scraping : {e}")

# ----------------------
# 7. BOUCLE BOT
# ----------------------
def bot_loop():
    while True:
        check_vinted()
        delay = MIN_INTERVAL + random.uniform(0, MAX_JITTER)
        logger.info(f"⏰ Prochaine vérification dans {int(delay)} secondes")
        time.sleep(delay)

# ----------------------
# 8. LANCEMENT
# ----------------------
if __name__ == "__main__":
    logger.info("🚀 Bot Vinted Requests démarré")
    logger.info(f"📡 URL Vinted : {VINTED_URL}")
    bot_loop()
