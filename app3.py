import json
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin
import time
import re
import random
import os , io
import unicodedata
from DB.db import db_execute
from io import BytesIO
from PIL import ImageFilter
from PIL import Image, ImageDraw, ImageFont
import arabic_reshaper
from bidi.algorithm import get_display
from ML.ai import classify_news, TEMPLATES
from dotenv import load_dotenv
from DB.db import get_conn
from DB.cloud_storage import upload_image
from services.queue_manager import QueueManager
import time
from threading import Thread
from services.scheduler import publishing_worker
from services.recalculation_worker import recalculation_worker
from services.date_filter import is_within_range
from datetime import datetime
from utils.logger import logger
from tenacity import retry, stop_after_attempt, wait_fixed
from supabase import create_client
import traceback
# =========================
# LOAD ENV
# =========================
queue = QueueManager()

load_dotenv()

TOKEN = os.getenv("TOKEN")
CHAT_ID = os.getenv("CHAT_ID")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
# =========================
# PATHS
# =========================

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

TEMPLATES_DIR = os.path.join(BASE_DIR, "templates")

# OUTPUT_FOLDER = "generated"

# os.makedirs(OUTPUT_FOLDER, exist_ok=True)



# =========================
# DATABASE
# =========================


# =========================
# TEMPLATE CONFIG
# =========================

TEMPLATE_CONFIG = {

    "رياضة": {
        "template": os.path.join(TEMPLATES_DIR, "رياضة.png"),
        "image_box": (0, 0, 1080, 835),
        "text_box": (0, 940, 1060, 1200),
        "align": "center"
    },

    "سياسة": {
        "template": os.path.join(TEMPLATES_DIR, "سياسة.png"),
        "image_box": (0, 0, 1080, 820),
        "text_box": (340, 820, 1070, 1050),
        "align": "center"
    },

    "فن": {
        "template": os.path.join(TEMPLATES_DIR, "عام.png"),
        "image_box": (46, 188, 1040, 744),
        "text_box": (10, 845, 1070, 1210),
        "align": "center"
    },

    "اجتماعية": {
        "template": os.path.join(TEMPLATES_DIR, "اجتماعية.png"),
        "image_box": (46, 188, 1040, 744),
        "text_box": (10, 845, 1070, 1210),
        "align": "center"
    },

    "عام": {
        "template": os.path.join(TEMPLATES_DIR, "عام.png"),
        "image_box": (46, 188, 1040, 744),
        "text_box": (10, 845, 1070, 1210),
        "align": "center"
    }

}

# =========================
# CATEGORY MAP
# =========================

MAP = {
    "sports": "رياضة",
    "politics": "سياسة",
    "art": "فن",
    "social": "اجتماعية"
}

# =========================
# CONFIG
# =========================

BASE_URL = "https://mnsht.net"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
}

FONT_PATH = "Cairo-Black.ttf"

MAX_FONT_SIZE = 60
MIN_FONT_SIZE = 26

TEXT_COLOR = (255, 255, 255)

# =========================
# SESSION
# =========================

session = requests.Session()
session.headers.update(HEADERS)

logger.info("🚀 APP STARTED")
logger.info("📰 WAITING FOR NEWS...")

# =========================
# HELPERS
# =========================

def clean_text(text):
    return unicodedata.normalize("NFKC", str(text or ""))

@retry(
    stop=stop_after_attempt(3),
    wait=wait_fixed(5)
)
def send_photo(photo_file, title, url, category, confidence, content):

    api_url = f"https://api.telegram.org/bot{TOKEN}/sendPhoto"

    title = clean_text(title)
    content = clean_text(content or "")

    short_content = (
        content[:500] + "..."
        if len(content) > 500
        else content
    )

    caption = f"""
📂 التصنيف: {category}
🎯 الثقة: {round(confidence * 100, 1)}%

📝 {short_content}

📌 اضغط على الزر لقراءة التفاصيل
"""

    keyboard = {
        "inline_keyboard": [
            [
                {
                    "text": "📖 Read More",
                    "url": url
                }
            ],
            [
                {
                    "text": "🔗 Share",
                    "url": f"https://t.me/share/url?url={url}&text={title}"
                }
            ]
        ]
    }

    file_to_close = None

    try:

        # =====================
        # HANDLE PATH OR BUFFER
        # =====================

        if isinstance(photo_file, str):
            file_to_send = open(photo_file, "rb")
            file_to_close = file_to_send
        else:
            file_to_send = photo_file
            file_to_send.seek(0)

        requests.post(
            api_url,
            data={
                "chat_id": CHAT_ID,
                "caption": caption,
                "reply_markup": json.dumps(keyboard),
                "parse_mode": "HTML"
            },
            files={
                "photo": file_to_send
            },
            timeout=30
        )

        logger.info("✅ SENT TO TELEGRAM")

    except Exception as e:
        logger.info("❌ TELEGRAM ERROR:", e)

    finally:
        if file_to_close:
            file_to_close.close()
        

def get_html():

    response = session.get(BASE_URL, timeout=(10, 30) )

    response.raise_for_status()

    return response.text


def news_exists(url):
    result = db_execute(
        "SELECT id FROM news WHERE url = %s",
        (url,),
        fetch=True
    )
    return result is not None and len(result) > 0

def clean_image_url(src):

    if not src:
        return None

    full_url = urljoin(
        BASE_URL,
        src
    )

    # إزالة الكاش
    full_url = full_url.replace(
        "/UploadCache/libfiles/",
        "/Upload/libfiles/"
    )

    # إزالة المقاسات
    full_url = re.sub(
        r'/\d+x\d+o?/',
        '/',
        full_url
    )

    return full_url


def fetch_article_content(url, max_words=100):

    try:

        response = session.get(
            url,
            timeout=15
        )

        response.raise_for_status()

        soup = BeautifulSoup(
            response.text,
            "lxml"
        )

        tag = soup.select_one(
            "div.paragraph-list"
        )

        if not tag:
            return None

        paragraphs = tag.find_all("p")

        content = " ".join(
            p.get_text(strip=True)
            for p in paragraphs
        )

        words = content.split()

        # بنبني الكلام عند أقرب نقطة بعد الكلمة 45
        chunk = " ".join(words[:max_words])
        cutoff = " ".join(words[:45])
        search_area = chunk[len(cutoff):]
        dot_index = search_area.find(".")
        if dot_index != -1:
            content = cutoff + search_area[:dot_index + 1]
        else:
            content = chunk

        return content if content else None

    except Exception as e:

        logger.info("❌ ARTICLE CONTENT ERROR:", e)
        
        return None



# =========================
# ARABIC TEXT
# =========================

def prepare_ar_text(text):

    reshaped = arabic_reshaper.reshape(text)

    bidi_text = get_display(
        reshaped
    )

    return bidi_text


# =========================
# WRAP TEXT
# =========================

def wrap_text(
    draw,
    text,
    font,
    max_width
):

    words = text.split()

    lines = []

    current_line = ""

    for word in words:

        test_line = (
            current_line + " " + word
            if current_line else word
        )

        bbox = draw.textbbox(
            (0, 0),
            test_line,
            font=font
        )

        width = bbox[2] - bbox[0]

        if width <= max_width:

            current_line = test_line

        else:

            if current_line:
                lines.append(current_line)

            current_line = word

    if current_line:
        lines.append(current_line)

    return lines


def fit_text(
    draw,
    text,
    font_path,
    max_width,
    max_height
):

    best_font = None
    best_lines = None
    best_line_height = None

    for size in range(
        MAX_FONT_SIZE,
        MIN_FONT_SIZE - 1,
        -2
    ):

        font = ImageFont.truetype(
            font_path,
            size
        )

        lines = wrap_text(
            draw,
            text,
            font,
            max_width
        )

        line_height = size + 15

        total_height = (
            len(lines) *
            line_height
        )

        longest_line = 0

        for line in lines:

            bbox = draw.textbbox(
                (0, 0),
                line,
                font=font
            )

            width = bbox[2] - bbox[0]

            if width > longest_line:
                longest_line = width

        if (
            total_height <= max_height
            and
            longest_line <= max_width
        ):

            best_font = font
            best_lines = lines
            best_line_height = line_height

            break

    return (
        best_font,
        best_lines,
        best_line_height
    )

def generate_post_image(
    title,
    image_url,
    news_id,
    url,
    category,
    confidence,
    content,
    send_to_telegram=True   # 👈 مهم لتوحيد الجروبات
):

    logger.info(f"CATEGORY DEBUG: {category}")
    logger.info(f"AVAILABLE KEYS: {list(TEMPLATE_CONFIG.keys())}")

    try:

        # =====================
        # LOAD CONFIG
        # =====================

        config = TEMPLATE_CONFIG.get(category)

        if config is None:
            logger.info(f"⚠️ Unknown category: {category} → fallback to عام")
            config = TEMPLATE_CONFIG["عام"]

        image_x1, image_y1, image_x2, image_y2 = config["image_box"]
        text_x1, text_y1, text_x2, text_y2 = config["text_box"]

        TEXT_BOX_X = text_x1
        TEXT_BOX_Y = text_y1
        TEXT_BOX_WIDTH = text_x2 - text_x1
        TEXT_BOX_HEIGHT = text_y2 - text_y1

        # =====================
        # LOAD TEMPLATE
        # =====================

        template_path = config.get("template")

        if not template_path or not os.path.exists(template_path):
            logger.info(f"❌ TEMPLATE NOT FOUND: {template_path}")
            return None

        template = Image.open(template_path).convert("RGBA")

        # =====================
        # DOWNLOAD IMAGE
        # =====================

        news_img = None

        if image_url:
            try:
                response = session.get(image_url, timeout=20)
                response.raise_for_status()

                news_img = Image.open(
                    BytesIO(response.content)
                ).convert("RGBA")

            except Exception as e:
                logger.info(f"❌ IMAGE DOWNLOAD ERROR: {e}")
                news_img = None

        # =====================
        # LOAD TEMPLATE
        # =====================
        template_path = config.get("template")
        if not template_path or not os.path.exists(template_path):
            logger.info(f"❌ TEMPLATE NOT FOUND: {template_path}")
            return None
        template = Image.open(template_path).convert("RGBA")

        # =====================
        # DOWNLOAD IMAGE
        # =====================
        news_img = None
        if image_url:
            try:
                response = session.get(image_url, timeout=20)
                response.raise_for_status()
                news_img = Image.open(
                    BytesIO(response.content)
                ).convert("RGBA")
            except Exception as e:
                logger.info(f"❌ IMAGE DOWNLOAD ERROR: {e}")
                news_img = None

        # =====================
        # LAYER SYSTEM (الأول عشان base يكون جاهز)
        # =====================
        base = Image.new("RGBA", template.size, (0, 0, 0, 0))
        base.paste(template, (0, 0))

        # =====================
        # PROCESS IMAGE — CNN Style (Blur BG + Sharp FG)
        # =====================
        if news_img:
            box_w = image_x2 - image_x1
            box_h = image_y2 - image_y1
            img_w, img_h = news_img.size
            img_ratio = img_w / img_h
            box_ratio = box_w / box_h

            # ── 1. BACKGROUND: يملأ الـ box بالكامل + blur شديد ──
            if img_ratio > box_ratio:
                bg_h = box_h
                bg_w = int(box_h * img_ratio)
            else:
                bg_w = box_w
                bg_h = int(box_w / img_ratio)

            bg = news_img.resize((bg_w, bg_h), Image.LANCZOS).convert("RGBA")

            # crop من المنتصف عشان يملأ الـ box بالظبط
            bg_crop_x = (bg_w - box_w) // 2
            bg_crop_y = (bg_h - box_h) // 2
            bg = bg.crop((bg_crop_x, bg_crop_y, bg_crop_x + box_w, bg_crop_y + box_h))

            # blur احترافي
            bg = bg.filter(ImageFilter.GaussianBlur(radius=20))

            # تعتيم خفيف فوق الـ blur عشان الـ fg يبرز
            overlay = Image.new("RGBA", (box_w, box_h), (0, 0, 0, 80))
            bg = Image.alpha_composite(bg, overlay)

            # ── 2. FOREGROUND: يتمدد لأقصى حجم ممكن بدون قص ──
            if img_ratio > box_ratio:
                fg_w = box_w
                fg_h = int(box_w / img_ratio)
            else:
                fg_h = box_h
                fg_w = int(box_h * img_ratio)

            fg = news_img.resize((fg_w, fg_h), Image.LANCZOS).convert("RGBA")

            # توسيط الـ fg فوق الـ bg
            fg_x = (box_w - fg_w) // 2
            fg_y = (box_h - fg_h) // 2

            # ── 3. دمج BG + FG في layer واحد ──
            layer = Image.new("RGBA", (box_w, box_h), (0, 0, 0, 0))
            layer.paste(bg, (0, 0))
            layer.paste(fg, (fg_x, fg_y), fg)

            # ── 4. لصق على الـ base ──
            base.paste(layer, (image_x1, image_y1), layer)

        # =====================
        # COMPOSITE FINAL
        # =====================
        if category in ["عام", "اجتماعية", "فن"]:
            final_img = base
        else:
            # رياضة وسياسة: template فوق الصورة بـ alpha_composite
            background = Image.new("RGBA", template.size, (0, 0, 0, 255))
            background.paste(base, (0, 0), base)
            final_img = Image.alpha_composite(background, template)

        # =====================
        # TEXT DRAWING
        # =====================

        draw = ImageDraw.Draw(final_img)

        title = prepare_ar_text(clean_text(title))

        font, lines, line_height = fit_text(
            draw,
            title,
            FONT_PATH,
            TEXT_BOX_WIDTH,
            TEXT_BOX_HEIGHT
        )

        if not font:
            logger.info("❌ FONT FIT ERROR")
            return None

        lines.reverse()

        total_text_height = len(lines) * line_height

        y = TEXT_BOX_Y + ((TEXT_BOX_HEIGHT - total_text_height) // 2)

        for line in lines:

            bbox = draw.textbbox((0, 0), line, font=font)
            width = bbox[2] - bbox[0]

            x = TEXT_BOX_X + ((TEXT_BOX_WIDTH - width) // 2)

            # shadow
            draw.text((x + 2, y + 2), line, font=font, fill=(0, 0, 0))

            # main text
            draw.text(
                (x, y),
                line,
                font=font,
                fill=TEXT_COLOR,
                stroke_width=1,
                stroke_fill=TEXT_COLOR
            )

            y += line_height

        # =====================
        # SAVE FILE
        # =====================

        filename = f"news_{news_id}.jpg"
        upload_image(final_img, filename)

        public_url = supabase.storage.from_("generated").get_public_url(filename)

        # =====================
        # TELEGRAM SEND (OPTIONAL)
        # =====================

        if send_to_telegram:

            buffer = io.BytesIO()
            rgb_img = final_img.convert("RGB")

            rgb_img.save(buffer, format="JPEG", quality=85)
            buffer.seek(0)

            send_photo(
                buffer,
                title,
                url,
                category,
                confidence,
                content
            )

            logger.info("🖼️ IMAGE GENERATED + SENT")

        return public_url

    except Exception as e:
        logger.info(f"❌ IMAGE ERROR: {e}")
        return None

# =========================
# EXTRACT NEWS
# =========================

def extract_news(
    html,
    limit=5
):

    soup = BeautifulSoup(
        html,
        "lxml"
    )

    news_list = []

    cards = soup.find_all(
        "div",
        class_="item-card"
    )

    count = 0

    for card in cards:
        count += 1
        if count >= limit:
         
            break

        try:

            a_tag = card.find("a")

            if not a_tag:
                continue

            url = urljoin(
                BASE_URL,
                a_tag.get("href")
            )

            # 🔥 PostgreSQL-safe duplicate check
            if news_exists(url):
                continue

            h3 = card.find("h3")

            title = (
                h3.get_text(strip=True)
                if h3
                else "بدون عنوان"
            )

            img_tag = card.find("img")

            raw_img_src = None

            if img_tag:

                raw_img_src = (
                    img_tag.get("data-src")
                    or
                    img_tag.get("src")
                )

            final_image = clean_image_url(
                raw_img_src
            )

            if (
                final_image
                and
                "logo" in final_image.lower()
            ):

                final_image = None

            content = fetch_article_content(url)

            news_list.append({

                "title": clean_text(title),

                "url": url,

                "image": final_image,

                "content": clean_text(content)

            })

            count += 1

        except Exception as e:

            logger.info(
                f"❌ CARD ERROR: {e}"
            )
            

    return news_list

def save_news(news):

    for item in news:

        try:

            category, confidence = classify_news(
                item["title"],
                content=item.get("content")
            )

            # =====================
            # HANDLE UNKNOWN
            # =====================

            if category is None:
                logger.info(f"⚠️ LOW CONFIDENCE NEWS: {item['title']}")
                category = "عام"
                confidence = 0.0

            # =====================
            # VALIDATE CATEGORY
            # =====================

            if category not in TEMPLATE_CONFIG:
                category = "عام"

            # =====================
            # SAVE TO DB
            # =====================

            result = db_execute("""
                INSERT INTO news (
                    title,
                    url,
                    image,
                    category,
                    confidence,
                    content
                )
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (url) DO NOTHING
                RETURNING id
            """, (
                item["title"],
                item["url"],
                item["image"],
                category,
                confidence,
                item.get("content")
            ), fetch=True)

            # =====================
            # DUPLICATE CHECK
            # =====================

            if not result:
                logger.info(f"⚠️ ARTICLE ALREADY EXISTS: {item['title']}")
                continue

            news_id = None

            if isinstance(result, list) and len(result) > 0:
                news_id = result[0]["id"] if isinstance(result[0], dict) else result[0]

            elif isinstance(result, dict):
                news_id = result.get("id")

            else:
                news_id = result

            if not news_id:
                logger.info("❌ NO NEWS ID RETURNED")
                continue

            logger.info(f"\n🟢 NEW ARTICLE: {item['title']}")

            # =====================
            # IMAGE GENERATION (الأول قبل القائمة)
            # =====================

            image_url = generate_post_image(
                item["title"],
                item["image"],
                news_id,
                item["url"],
                category,
                confidence,
                item.get("content"),
                send_to_telegram=False
            )

            if not image_url:
                logger.info("❌ IMAGE GENERATION FAILED")
                continue

            # =====================
            # QUEUE (بعد الصورة عشان image_url يكون جاهز)
            # =====================

            article_date = datetime.utcnow()

            if is_within_range(article_date):
                queue.add_or_update_queue_item({
                    "article_id": news_id,
                    "title": item["title"],
                    "url": item["url"],
                    "content": item.get("content"),
                    "image_url": image_url,
                    "created_at": time.time()
                })

            # =====================
            # UPDATE QUEUE IMAGE
            # =====================

            db_execute("""
                UPDATE news_queue
                SET image_url = %s,
                    generated_image = %s
                WHERE article_id = %s
            """, (
                image_url,
                f"news_{news_id}.jpg",
                news_id
            ))

            # =====================
            # TRAINING DATA
            # =====================

            if confidence >= 0.65 and category != "عام":

                db_execute("""
                    INSERT INTO confirmed_training (
                        title,
                        category,
                        confidence
                    )
                    VALUES (%s, %s, %s)
                    ON CONFLICT (title) DO NOTHING
                """, (
                    item["title"],
                    category,
                    confidence
                ))

        except Exception as e:
            logger.info(f"❌ SAVE ERROR: {e}")
            traceback.print_exc()
# =========================
# MAIN LOOP
# =========================

def run():

    first_run = True

    while True:

        try:

            logger.info(
                f"\n🔄 Checking for news... "
                f"({time.strftime('%H:%M:%S')})"
            )

            html = get_html()

            limit = 5 if first_run else 50

            news = extract_news(
                html,
                limit=limit
            )

            first_run = False

            if news:

                save_news(news)

                logger.info(
                    f"✅ Added {len(news)} articles."
                )

            else:

                logger.info("😴 No new updates.")

        except requests.exceptions.RequestException as e:

            logger.info(f"🌐 NETWORK ERROR: {e}")

            time.sleep(10)

        except Exception as e:

            

            logger.info(f"⚠️ LOOP ERROR: {e}")

            time.sleep(5)
            

        time.sleep(random.randint(60, 120))


# =========================
# START
# =========================



if __name__ == "__main__":

    try:

        Thread(
            target=publishing_worker,
            daemon=True
        ).start()

        Thread(
            target=recalculation_worker,
            daemon=True
        ).start()

        logger.info("🚀 Workers started")

        run()

    except KeyboardInterrupt:

        logger.info("🛑 Stopped manually")

    except Exception as e:

        logger.error(f"CRASH: {e}")
