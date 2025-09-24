import time
import random
import os
import logging
import requests
import json
from bs4 import BeautifulSoup

# ----------------------
# 1. CONFIGURATION
# ----------------------
VINTED_URLS = os.getenv("VINTED_URLS", "").split(',')
DISCORD_WEBHOOK = os.getenv("DISCORD_WEBHOOK")
SEEN_FILE = "seen.json"
RUN_DURATION = 300  # durée du run en secondes 300 secondes soit 5 minutes

if not VINTED_URLS:
    raise SystemExit("⚠️ VINTED_URLS non configuré dans les Secrets.")
if not DISCORD_WEBHOOK:
    raise SystemExit("⚠️ DISCORD_WEBHOOK non configuré dans les Secrets.")

# ----------------------
# 2. LOGGING
# ----------------------
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("vinted-bot")

# ----------------------
# 3. SESSION HTTP
# ----------------------
session = requests.Session()
session.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept-Language": "fr-FR,fr;q=0.9"
})

# ----------------------
# 4. MEMOIRE PERSISTANTE
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
# 5. DISCORD
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
# 6. SCRAPER VINTED (one-shot)
# ----------------------
# ----------------------
# 6. SCRAPER VINTED (one-shot)
# ----------------------
def check_vinted():
    total_new_items = 0
    # Boucle sur chaque URL dans la liste
    for url in VINTED_URLS:
        logger.info(f"⏳ Analyse de l'URL : {url}")
        try:
            resp = session.get(url, timeout=12)
            if resp.status_code != 200:
                logger.warning(f"Réponse inattendue {resp.status_code} pour l'URL {url}")
                continue # Passe à l'URL suivante

            soup = BeautifulSoup(resp.text, "html.parser")
            container = soup.find("div", class_="feed-grid")
            if not container:
                logger.warning(f"❌ Container feed-grid non trouvé pour l'URL {url}")
                continue # Passe à l'URL suivante

            items = container.find_all("div", class_="feed-grid__item")
            logger.info(f"📦 {len(items)} annonces détectées sur la page {url}")

            new_items_count = 0
            for item in items[:20]:
                try:
                    # Lien
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
                except Exception as e:
                    logger.error(f"Erreur traitement annonce pour l'URL {url}: {e}")

            total_new_items += new_items_count

        except Exception as e:
            logger.error(f"Erreur scraping pour l'URL {url}: {e}")

    save_seen(seen_items)
    logger.info("💾 Fichier seen.json mis à jour après ce scraping")

    if total_new_items == 0:
        logger.info("✅ Aucune nouvelle annonce sur toutes les URL")
    else:
        logger.info(f"📬 {total_new_items} nouvelles annonces envoyées au total")

# ----------------------
# 7. BOUCLE BOT AVEC DUREE LIMITEE
# ----------------------
def bot_loop():
    end_time = time.time() + RUN_DURATION
    while time.time() < end_time:
        logger.info("⏳ Nouvelle analyse...")
        check_vinted()

        # Sleep aléatoire mais ne dépasse pas la fin du run
        delay = random.uniform(180, 360)  # 3 à 6 minutes
        time_remaining = end_time - time.time()
        if time_remaining <= 0:
            break
        sleep_time = min(delay, time_remaining)
        logger.info(f"⏱ Prochaine analyse dans {int(sleep_time)} secondes")
        time.sleep(sleep_time)

    logger.info("🏁 Fin du run")

# ----------------------
# 8. LANCEMENT
# ----------------------
if __name__ == "__main__":
    logger.info("🚀 Bot Vinted démarré (one-shot)")
    logger.info(f"📡 URL Vinted : {VINTED_URLS}")
    bot_loop()
