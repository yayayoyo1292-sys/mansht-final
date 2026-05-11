
import json
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin
import time
import re
import os
import unicodedata
from db import db_execute
from io import BytesIO
from PIL import ImageFilter
from PIL import Image, ImageDraw, ImageFont
import arabic_reshaper
from bidi.algorithm import get_display
from ai import classify_news, TEMPLATES
from dotenv import load_dotenv
from db import get_conn
from cloud_storage import upload_image

# =========================
# LOAD ENV
# =========================

load_dotenv()

TOKEN = os.getenv("TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

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
                print("⚠️ LOW CONFIDENCE NEWS:", item["title"])
                category = "عام"
                confidence = 0.0

            # =====================
            # VALIDATE CATEGORY
            # =====================

            if category not in TEMPLATE_CONFIG:
                category = "عام"

            # =====================
            # SAVE TO DB (USING DB_EXECUTE)
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

            # duplicate
            if not result:
                print("⚠️ ARTICLE ALREADY EXISTS:", item["title"])
                continue

            news_id = result[0]
            filename = f"news_{news_id}.png"
            print("\n🟢 NEW ARTICLE")
            print(f"TITLE: {item['title']}")

            # =====================
            # GENERATE IMAGE
            # =====================

            generate_post_image(
                item["title"],
                item["image"],
                news_id,
                item["url"],
                category,
                confidence,
                item.get("content")
            )

            # =====================
            # SAVE TRAINING DATA
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
            print(f"❌ SAVE ERROR: {e}")

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
        "image_box": (0, 0, 1080, 835),
        "text_box": (340, 820, 1070, 1050),
        "align": "center"
    },

    "فن": {
        "template": os.path.join(TEMPLATES_DIR, "فن.png"),
        "image_box": (0, 210, 1080, 1070),
        "text_box": (50, 1050, 1030, 1280),
        "align": "center"
    },

    "اجتماعية": {
        "template": os.path.join(TEMPLATES_DIR, "اجتماعية.png"),
        "image_box": (35, 180, 1050, 758),
        "text_box": (10, 845, 1070, 1210),
        "align": "center"
    },

    "عام": {
        "template": os.path.join(TEMPLATES_DIR, "عام.png"),
        "image_box": (35, 180, 1050, 758),
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

print("🚀 APP STARTED")
print("📰 WAITING FOR NEWS...")

# =========================
# HELPERS
# =========================

def clean_text(text):
    return unicodedata.normalize("NFKC", str(text or ""))


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

        print("✅ SENT TO TELEGRAM")

    except Exception as e:
        print("❌ TELEGRAM ERROR:", e)

    finally:
        if file_to_close:
            file_to_close.close()
        

def get_html():

    response = session.get(
        BASE_URL,
        timeout=20
    )

    response.raise_for_status()

    return response.text


def news_exists(url):
    result = db_execute(
        "SELECT id FROM news WHERE url = %s",
        (url,),
        fetch=True
    )
    return result is not None

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


def fetch_article_content(url, max_words=50):

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

        content = " ".join(
            words[:max_words]
        )

        return content if content else None

    except Exception as e:

        print("❌ ARTICLE CONTENT ERROR:", e)
        
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
    content
):

    print("CATEGORY DEBUG:", category)
    print("AVAILABLE KEYS:", TEMPLATE_CONFIG.keys())

    try:

        # =====================
        # LOAD CONFIG
        # =====================

        config = TEMPLATE_CONFIG.get(category)

        if config is None:
            print(f"⚠️ Unknown category: {category} → fallback to عام")
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

        if not os.path.exists(template_path):
            print(f"❌ TEMPLATE NOT FOUND: {template_path}")
            return

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
                print("❌ IMAGE DOWNLOAD ERROR:", e)
                news_img = None

        # =====================
        # PROCESS IMAGE
        # =====================

        if news_img:

            img_ratio = news_img.width / news_img.height

            target_ratio = (
                (image_x2 - image_x1) /
                (image_y2 - image_y1)
            )

            if img_ratio > target_ratio:
                new_width = int(news_img.height * target_ratio)

                left = (news_img.width - new_width) // 2

                news_img = news_img.crop((
                    left, 0,
                    left + new_width,
                    news_img.height
                ))
            else:
                new_height = int(news_img.width / target_ratio)

                top = (news_img.height - new_height) // 2

                news_img = news_img.crop((
                    0, top,
                    news_img.width,
                    top + new_height
                ))

            news_img = news_img.resize(
                (image_x2 - image_x1, image_y2 - image_y1),
                Image.LANCZOS
            )

        # =====================
        # LAYER SYSTEM
        # =====================

        base = Image.new("RGBA", template.size, (0, 0, 0, 0))
        base.paste(template, (0, 0))

        if category in ["عام", "اجتماعية"]:

            if news_img:
                base.paste(news_img, (image_x1, image_y1), news_img)

            final_img = base

        else:

            background = Image.new("RGBA", template.size, (0, 0, 0, 255))

            if news_img:
                background.paste(news_img, (image_x1, image_y1))

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
            print("❌ FONT FIT ERROR")
            return

        lines.reverse()

        total_text_height = len(lines) * line_height

        y = TEXT_BOX_Y + (
            (TEXT_BOX_HEIGHT - total_text_height) // 2
        )

        for line in lines:

            bbox = draw.textbbox((0, 0), line, font=font)
            width = bbox[2] - bbox[0]

            x = TEXT_BOX_X + (
                (TEXT_BOX_WIDTH - width) // 2
            )

            draw.text((x + 2, y + 2), line, font=font, fill=(0, 0, 0))

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
        # CLOUD UPLOAD (BACKUP)
        # =====================

        filename = f"news_{news_id}.png"
        upload_image(final_img, filename)

        # =====================
        # TELEGRAM SEND (FROM MEMORY)
        # =====================

        import io

        buffer = io.BytesIO()
        final_img.save(buffer, format="PNG")
        buffer.seek(0)

        send_photo(
            buffer,
            None,
            url,
            category,
            confidence,
            content
        )

        print("🖼️ IMAGE GENERATED + SENT")

    except Exception as e:
        print(f"❌ IMAGE ERROR: {e}")

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

            print(
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
                print("⚠️ LOW CONFIDENCE NEWS:", item["title"])
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

            # duplicate check
            if not result:
                print("⚠️ ARTICLE ALREADY EXISTS:", item["title"])
                continue

            news_id = result[0]

            print("\n🟢 NEW ARTICLE")
            print(f"TITLE: {item['title']}")

            # =====================
            # GENERATE IMAGE
            # =====================

            generate_post_image(
                item["title"],
                item["image"],
                news_id,
                item["url"],
                category,
                confidence,
                item.get("content")
            )

            # =====================
            # SAVE TRAINING DATA
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
            print(f"❌ SAVE ERROR: {e}")
# =========================
# MAIN LOOP
# =========================

def run():

    first_run = True

    while True:

        try:

            print(
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

                print(
                    f"✅ Added {len(news)} articles."
                )

            else:

                print("😴 No new updates.")

        except requests.exceptions.RequestException as e:

            print(f"🌐 NETWORK ERROR: {e}")

            time.sleep(10)

        except Exception as e:

            

            print(f"⚠️ LOOP ERROR: {e}")

            time.sleep(5)
            

        time.sleep(90)


# =========================
# START
# =========================

if __name__ == "__main__":

    try:

        run()

    finally:
        print("🔌 DATABASE CONNECTION CLOSED")
