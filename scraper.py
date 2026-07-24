import requests
from bs4 import BeautifulSoup
import json
import os
import re
import traceback
from dotenv import load_dotenv
from telegram import Bot

# Carica le variabili dal file .env
load_dotenv()

# Configurazione
BASE_URL = "https://www.concorsipubblici.com"
URL = f"{BASE_URL}/concorsi/occupazione/pro/settore-informatico-600"
DATA_FILE = "concorsi_visti.json"
MAX_VISTI = 100  # aumentata a 100
TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

# File per il conteggio dei fallimenti consecutivi
FAILURE_COUNTER_FILE = "failures_counter.json"
MAX_CONSECUTIVE_FAILURES = 3

# Funzione per normalizzare gli URL
def normalize_url(url):
    """Rende gli URL comparabili rimuovendo slash finali e convertendo a minuscolo."""
    return url.rstrip('/').lower()

# ------------------------------------------------------------------
# Funzioni per gestire il contatore dei fallimenti consecutivi
# ------------------------------------------------------------------
def load_failures_counter():
    """Carica il contatore dei fallimenti consecutivi dal file JSON."""
    if os.path.exists(FAILURE_COUNTER_FILE):
        try:
            with open(FAILURE_COUNTER_FILE, "r") as f:
                data = json.load(f)
                return data.get("count", 0)
        except (json.JSONDecodeError, IOError):
            return 0
    return 0

def save_failures_counter(count):
    """Salva il contatore dei fallimenti consecutivi nel file JSON."""
    with open(FAILURE_COUNTER_FILE, "w") as f:
        json.dump({"count": count}, f)

def reset_failures_counter():
    """Resetta il contatore dei fallimenti consecutivi."""
    if os.path.exists(FAILURE_COUNTER_FILE):
        os.remove(FAILURE_COUNTER_FILE)

# ------------------------------------------------------------------
# Funzioni esistenti (modificate)
# ------------------------------------------------------------------
def load_concorsi_visti():
    """Carica la lista degli URL dei concorsi già notificati (tutti)."""
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, 'r') as f:
            try:
                data = json.load(f)
                if isinstance(data, list):
                    return data
            except json.JSONDecodeError:
                pass
    return []

def save_concorsi_visti(visti_list):
    """Salva la lista degli URL mantenendo solo gli ultimi 100 in ordine cronologico."""
    with open(DATA_FILE, 'w') as f:
        # Normalizza gli URL prima di salvarli
        normalized_visti = [normalize_url(url) for url in visti_list]
        json.dump(normalized_visti[-MAX_VISTI:], f, indent=2)

def estrai_concorsi():
    """Estrae i concorsi solo dal contenitore <div class="views-rows">."""
    response = requests.get(URL)
    response.raise_for_status()  # solleva eccezione se HTTP non 200
    soup = BeautifulSoup(response.text, 'html.parser')
    concorsi = []
    # Trova il contenitore principale
    container = soup.find('div', class_='views-rows')
    if container:
        # Itera su tutti gli <h2> all'interno del container
        for item in container.find_all('h2'):
            link = item.find('a')
            if not link:
                continue
            href = link.get('href')
            if not href:
                continue
            # Costruisce URL assoluto come identificativo univoco
            if href.startswith('/'):
                url_concorso = BASE_URL + href
            else:
                url_concorso = href
            # Normalizza l'URL
            url_concorso = normalize_url(url_concorso)
            concorso_id = link.text.strip()
            parent = item.parent
            dettagli = {}
            # Estrai ente
            ente_elem = parent.find(string=re.compile(r'Ente', re.IGNORECASE))
            if ente_elem:
                ente_link = ente_elem.parent.find('a')
                if ente_link:
                    dettagli['ente'] = ente_link.text.strip()
            # Estrai scadenza
            scadenza_elem = parent.find(string=re.compile(r'Scadenza', re.IGNORECASE))
            if scadenza_elem:
                scadenza = scadenza_elem.parent.find_next('div').text.strip()
                dettagli['scadenza'] = scadenza
            # Estrai località
            localita_elem = parent.find(string=re.compile(r'Località', re.IGNORECASE))
            if localita_elem:
                localita = localita_elem.parent.find_next('div').text.strip()
                dettagli['localita'] = localita
            # Estrai occupazione
            occupazione_elem = parent.find(string=re.compile(r'Occupazione', re.IGNORECASE))
            if occupazione_elem:
                occupazione = occupazione_elem.parent.find_next('div').text.strip()
                dettagli['occupazione'] = occupazione
            # Estrai posti
            posti_elem = parent.find(string=re.compile(r'Posti', re.IGNORECASE))
            if posti_elem:
                posti = posti_elem.parent.find_next('div').text.strip()
                dettagli['posti'] = posti
            # Estrai descrizione
            descrizione_elem = parent.find('p') or parent.find('div', class_=re.compile(r'descrizione|testo', re.IGNORECASE))
            if descrizione_elem:
                dettagli['descrizione'] = descrizione_elem.text.strip()
            concorsi.append({
                'id': concorso_id,
                'url': url_concorso,
                'dettagli': dettagli
            })
    return concorsi

async def invia_telegram(concorso):
    """Invia notifica via Telegram con tutti i dettagli disponibili."""
    bot = Bot(token=TELEGRAM_TOKEN)
    message = f"🆕 *Nuovo concorso informatico!*\n\n"
    message += f"📌 *{concorso['id']}*\n"
    message += f"🔗 {concorso['url']}\n"
    if 'ente' in concorso['dettagli']:
        message += f"Ente: {concorso['dettagli']['ente']}\n"
    # Tronca i campi lunghi a 50 caratteri
    if 'scadenza' in concorso['dettagli']:
        scadenza = concorso['dettagli']['scadenza'][:50]
        message += f"Scadenza: {scadenza}\n"
    if 'localita' in concorso['dettagli']:
        localita = concorso['dettagli']['localita'][:50]
        message += f"Località: {localita}\n"
    if 'occupazione' in concorso['dettagli']:
        occupazione = concorso['dettagli']['occupazione'][:50]
        message += f"Occupazione: {occupazione}\n"
    if 'posti' in concorso['dettagli']:
        posti = concorso['dettagli']['posti'][:50]
        message += f"Posti: {posti}\n"
    if 'descrizione' in concorso['dettagli']:
        message += f"\nDettagli:\n{concorso['dettagli']['descrizione']}\n"
    await bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=message, parse_mode='Markdown')

async def invia_avviso_telegram(testo):
    """Invia un semplice avviso Telegram (usato per i fallimenti consecutivi)."""
    bot = Bot(token=TELEGRAM_TOKEN)
    await bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=testo, parse_mode='HTML')

# ------------------------------------------------------------------
# Logica principale con gestione dei fallimenti consecutivi
# ------------------------------------------------------------------
async def main():
    # Carica il contatore dei fallimenti consecutivi
    consecutive_failures = load_failures_counter()

    try:
        concorsi = estrai_concorsi()

        # Se la lista è vuota, consideralo un fallimento
        if not concorsi:
            consecutive_failures += 1
            save_failures_counter(consecutive_failures)
            print("Nessun concorso estratto, considerata come fallimento.")
            # Esci dal flusso principale: il prossimo cron job proverà di nuovo
            return

        # Success: resetta il contatore dei fallimenti
        reset_failures_counter()

        concorsi_visti = load_concorsi_visti()
        concorsi_nuovi = []
        for concorso in concorsi:
            normalized_current = normalize_url(concorso['url'])
            # Controlla se l'URL normalizzato è già presente nella lista
            if not any(normalize_url(u) == normalized_current for u in concorsi_visti):
                concorsi_nuovi.append(concorso)
                concorsi_visti.append(normalize_url(concorso['url']))
        for concorso in concorsi_nuovi:
            await invia_telegram(concorso)
            print(f"Notificato: {concorso['url']}")
        save_concorsi_visti(concorsi_visti)
        print(f"Trovati {len(concorsi_nuovi)} nuovi concorsi su {len(concorsi)} totali")

    except requests.exceptions.HTTPError as e:
        # Errore HTTP (es. 500, 404, ecc.)
        consecutive_failures += 1
        save_failures_counter(consecutive_failures)
        status_code = e.response.status_code if e.response is not None else "N/A"
        error_msg = f"Errore HTTP {status_code}"
        print(f"{error_msg} (tentativo {consecutive_failures}/{MAX_CONSECUTIVE_FAILURES})")

        if consecutive_failures >= MAX_CONSECUTIVE_FAILURES:
            await invia_avviso_telegram(
                f"⚠️ <b>Avviso Scraper</b> ⚠️\n\n"
                f"Lo scraper ha fallito <b>{MAX_CONSECUTIVE_FAILURES} volte consecutive</b>.\n"
                f"Ultimo errore: <code>{error_msg}</code>"
            )
            reset_failures_counter()

    except Exception as e:
        # Altri errori (es. sito irraggiungibile, errore di rete)
        consecutive_failures += 1
        save_failures_counter(consecutive_failures)
        error_msg = str(e)
        print(f"Errore durante lo scraping (tentativo {consecutive_failures}/{MAX_CONSECUTIVE_FAILURES}): {error_msg}")

        if consecutive_failures >= MAX_CONSECUTIVE_FAILURES:
            await invia_avviso_telegram(
                f"⚠️ <b>Avviso Scraper</b> ⚠️\n\n"
                f"Lo scraper ha fallito <b>{MAX_CONSECUTIVE_FAILURES} volte consecutive</b>.\n"
                f"Ultimo errore: <code>{error_msg[:4096]}</code>"
            )
            reset_failures_counter()

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
