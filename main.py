import os
import requests
from bs4 import BeautifulSoup
import time
import random
import logging
from flask import Flask
import threading

# ----------------------
# 1. CONFIGURATION
# ----------------------
VINTED_URL = os.getenv("VINTED_URL")
DISCORD_WEBHOOK = os.getenv("DISCORD_WEBHOOK")  # <- le secret GitHub doit s'appeler exactement DISCORD_WEBHOOK

if not VINTED_URL:
    raise SystemExit("⚠️ VINTED_URL non configuré dans les Secrets.")
if not DISCORD_WEBHOOK:
    raise SystemExit("⚠️ DISCORD_WEBHOOK non configuré dans les Secrets.")

seen_items = set()

MIN_INTERVAL = 180
MAX_JITTER = 120
MAX_RETRIES = 5
BACKOFF_BASE = 15
REQUEST_TIMEOUT = 12

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
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "fr-FR,fr;q=0.9,en-US;q=0.8,en;q=0.7",
    "Referer": "https://www.vinted.fr/"
})

# ----------------------
# 4. ENVOI DISCORD
# ----------------------
def send_to_discord(title, price, link, img_url):
    data = {
        "embeds": [
            {
                "title": f"{title} - {price}",
                "url": link,
                "image": {"url": img_url},
                "color": 3447003
            }
        ]
    }
    try:
        resp = session.post(DISCORD_WEBHOOK, json=data, timeout=10)
        if resp.status_code // 100 != 2:
            logger.warning(f"Discord Webhook renvoyé {resp.status_code}")
    except Exception as e:
        logger.error(f"Erreur en envoyant à Discord : {e}")

# ----------------------
# 5. SCRAPER VINTED
# ----------------------
from bs4 import BeautifulSoup

def parse_vinted_list(html):
    soup = BeautifulSoup(html, "html.parser")
    
    # On récupère tous les div qui contiennent les annonces
    items = soup.find_all("div", class_=lambda x: x and "box--item-details" in x)
    
    annonces = []
    for item in items:
        try:
            # Titre
            title_tag = item.find("h1", class_="web_ui__Text__text web_ui__Text__title web_ui__Text__left")
            title = title_tag.get_text(strip=True) if title_tag else "Sans titre"
            
            # Prix
            price_tag = item.find("p", class_="web_ui__Text__text web_ui__Text__subtitle web_ui__Text__left")
            price = price_tag.get_text(strip=True) if price_tag else "Prix non affiché"
            
            # Lien
            link_tag = item.find("a", href=True)
            link = "https://www.vinted.fr" + link_tag['href'] if link_tag else ""
            
            # Image
            img_tag = item.find("img")
            img = img_tag.get("src") if img_tag else ""
            
            # Ajouter à la liste des annonces
            annonces.append({
                "title": title,
                "price": price,
                "link": link,
                "img": img
            })
        except Exception as e:
            print(f"Erreur lors du parsing d'une annonce: {e}")
    
    return annonces





def check_vinted():
    retries = 0
    while True:
        try:
            resp = session.get(VINTED_URL, timeout=REQUEST_TIMEOUT)
            if resp.status_code == 200:
                items = parse_vinted_list(resp.text)
                new_items_count = 0

                for item in items:
                    link = item["link"]
                    if link in seen_items:
                        continue
                    seen_items.add(link)
                    new_items_count += 1

                    title = item["title"]
                    price = item["price"]
                    img = item["img"]

                    # Log et envoi Discord
                    logger.info(f"📦 Nouvelle annonce : {title} - {price}\n🔗 {link}")
                    send_to_discord(title, price, link, img)

                if new_items_count == 0:
                    logger.info(f"✅ Aucune nouvelle annonce ({len(items)} vérifiées)")
                else:
                    logger.info(f"📬 {new_items_count} nouvelles annonces envoyées")
                return

            elif resp.status_code in (429, 503, 502):
                raise requests.HTTPError(f"Status {resp.status_code}")
            else:
                logger.warning(f"Réponse inattendue {resp.status_code}")
                return

        except Exception as e:
            retries += 1
            if retries > MAX_RETRIES:
                backoff = BACKOFF_BASE * (2 ** (retries - MAX_RETRIES))
                logger.warning(f"Erreur persistante {e}. Pause {backoff}s.")
                time.sleep(backoff)
                return
            else:
                sleep_time = random.uniform(2,5)
                logger.debug(f"Erreur {e}, retry dans {sleep_time:.1f}s (essai {retries}/{MAX_RETRIES})")
                time.sleep(sleep_time)


# ----------------------
# 6. BOUCLE BOT
# ----------------------
def bot_loop():
    while True:
        try:
            check_vinted()
            delay = MIN_INTERVAL + random.uniform(0, MAX_JITTER)
            logger.info(f"⏰ Prochaine vérification dans {int(delay)} secondes")
            time.sleep(delay)
        except Exception as e:
            logger.error(f"⚠️ Erreur critique : {e}")
            time.sleep(60)

# ----------------------
# 7. SERVEUR FLASK
# ----------------------
app = Flask(__name__)

@app.route("/")
def home():
    logger.info("💡 Ping reçu de UptimeRobot")
    return "✅ Vinted bot tourne bien !"

def run_flask():
    app.run(host="0.0.0.0", port=8080)

# ----------------------
# 8. LANCEMENT
# ----------------------
if __name__ == "__main__":
    logger.info("🚀 Bot Vinted démarré")
    logger.info(f"📡 URL Vinted : {VINTED_URL}")

    t1 = threading.Thread(target=bot_loop, daemon=True)
    t1.start()

    run_flask()
