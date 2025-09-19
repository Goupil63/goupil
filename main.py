import os
import time
import random
import logging
import requests
import json
from bs4 import BeautifulSoup

# ----------------------
# 1. CONFIGURATION
# ----------------------
VINTED_URL = os.getenv("VINTED_URL")  # ex: "https://www.vinted.fr/catalog?search_text=sac&order=newest_first"
DISCORD_WEBHOOK = os.getenv("DISCORD_WEBHOOK")

if not VINTED_URL:
    raise SystemExit("⚠️ VINTED_URL non configuré dans les Secrets.")
if not DISCORD_WEBHOOK:
    raise SystemExit("⚠️ DISCORD_WEBHOOK non configuré dans les Secrets.")

MIN_INTERVAL = 180  # 3 minutes
MAX_JITTER = 120    # jusqu'à 2 minutes aléatoires

SEEN_FILE = "seen.json"

# ----------------------
# 2. LOGGING
# ----------------------
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("vinted-bot")

# ----------------------
# 3. MÉMOIRE PERSISTANTE
# ----------------------
def load_seen():
    if os.path.exists(SEEN_FILE):
        try:
            with open(SEEN_FILE, "r", encoding="utf-8") as f:
                return set(json.load(f))
        except Exception as e:
            logger.error(f"Erreur lecture {SEEN_FILE}: {e}")
    return set()

def save_seen(seen_items):
    try:
        with open(SEEN_FILE, "w", encoding="utf-8") as f:
            json.dump(list(seen_items), f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"Erreur écriture {SEEN_FILE}: {e}")

seen_items = load_seen()
logger.info(f"📂 {len(seen_items)} annonces déjà connues (mémoire persistante)")

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
def send_to_discord(title, price, link):
    data = {
        "embeds": [{
            "title": f"{title} - {price}",
            "url": link,
            "color": 3447003
        }]
    }
    try:
        resp = session.post(DISCORD_WEBHOOK, json=data, timeout=10)
        if resp.status_code == 429:
            logger.warning("⚠️ Rate limit Discord (429). Message ignoré.")
        elif resp.status_code // 100 != 2:
            logger.warning(f"⚠️ Discord Webhook renvoyé {resp.status_code}")
    except Exception as e:
        logger.error(f"Erreur en envoyant à Discord : {e}")

# ----------------------
# 6. SCRAPER VINTED
# ----------------------
def check_vinted():
    global seen_items
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
                # Titre : première ligne du texte visible
                title = item.get_text(separator="\n").split("\n")[0]

                # Lien
                link_tag = item.find("a", href=True)
                link = "https://www.vinted.fr" + link_tag['href'] if link_tag else "Lien non trouvé"

                # Prix
                price_tag = item.find("div", {"data-testid": "item-price"})
                price = price_tag.get_text(strip=True) if price_tag else "Prix non trouvé"

                # Ignorer les annonces déjà vues
                if link in seen_items:
                    continue
                seen_items.add(link)
                save_seen(seen_items)
                new_items_count += 1

                logger.info(f"📬 Nouvelle annonce : {title} - {price}\n🔗 {link}")
                send_to_discord(title, price, link)

            except Exception as e:
                logger.error(f"Erreur traitement annonce : {e}")

        if new_items_count == 0:
            logger.info("✅ Aucune nouvelle annonce")
        else:
            logger.info(f"📬 {new_items_count} nouvelles annonces envoyées")

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
