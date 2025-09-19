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
DISCORD_WEBHOOK = os.getenv("DISCORD_WEBHOOK")

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
def parse_vinted_list(html):
    soup = BeautifulSoup(html, "html.parser")
    items = soup.find_all("div", {"data-testid": "item"})
    if not items:
        items = soup.find_all("div", class_=lambda x: x and any(cls in str(x).lower() for cls in ["item-box", "feed-grid-item", "item"]) if x else False)
    if not items:
        items = soup.select("a[href*='/articles/']")
    return items

def check_vinted():
    retries = 0
    while True:
        try:
            resp = session.get(VINTED_URL, timeout=REQUEST_TIMEOUT)
            if resp.status_code == 200:
                items = parse_vinted_list(resp.text)

                # Construction liste avec ID pour tri chronologique
                items_with_id = []
                for item in items:
                    try:
                        link_tag = item if item.name == "a" else item.find("a", href=True)
                        if not link_tag: continue
                        href = link_tag.get("href")
                        if not href: continue
                        link = href if href.startswith("http") else "https://www.vinted.fr" + href

                        item_id = item.get("data-id") or item.get("data-item-id") or 0
                        items_with_id.append((item_id, item, link))
                    except:
                        continue

                # Tri par ID croissant (plus récent en dernier)
                items_with_id.sort(key=lambda x: x[0])

                new_items_count = 0
                for item_id, item, link in items_with_id:
                    try:
                        if link in seen_items:
                            continue
                        seen_items.add(link)
                        new_items_count += 1

                        # Titre
                        title = "Sans titre"
                        for selector in ["h3","h2","h1","[data-testid*='title']",".item-title"]:
                            title_element = item.select_one(selector) if "." in selector or "[" in selector else item.find(selector)
                            if title_element:
                                title = title_element.get_text(strip=True)
                                break

                        # Prix
                        price = "Prix non affiché"
                        for selector in ["span[class*='text']", "[data-testid*='price']", ".item-price", "*[class*='price']"]:
                            price_element = item.select_one(selector)
                            if price_element and "€" in price_element.get_text():
                                price = price_element.get_text(strip=True)
                                break

                        # Image
                        img = ""
                        img_element = item.find("img")
                        if img_element:
                            img_src = img_element.get("src") or img_element.get("data-src")
                            img = str(img_src) if img_src else ""

                        # LOG + Discord
                        logger.info(f"📦 Nouvelle annonce : {title} - {price}\n🔗 {link}")
                        send_to_discord(title, price, link, img)
                    except Exception as e:
                        logger.error(f"Erreur traitement annonce: {e}")

                if new_items_count == 0:
                    logger.info(f"✅ Aucune nouvelle annonce ({len(items_with_id)} vérifiées)")
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
    backoff = 60
    while True:
        try:
            check_vinted()
            delay = MIN_INTERVAL + random.uniform(0, MAX_JITTER)
            logger.info(f"⏰ Prochaine vérification dans {int(delay)} secondes")
            time.sleep(delay)
            backoff = 60
        except Exception as e:
            logger.error(f"⚠️ Erreur critique : {e}, backoff {backoff}s")
            time.sleep(backoff)
            backoff = min(backoff * 2, 3600)

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
    logger.info("🚀 Bot Vinted (ultra sécurisé) démarré")
    logger.info(f"📡 URL Vinted : {VINTED_URL}")

    # Thread bot
    t1 = threading.Thread(target=bot_loop, daemon=True)
    t1.start()

    # Flask pour UptimeRobot
    run_flask()
