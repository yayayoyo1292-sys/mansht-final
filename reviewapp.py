from fastapi import FastAPI
from pydantic import BaseModel
from db import get_conn

app = FastAPI()

LOCK_TIMEOUT_MINUTES = 10


# =========================
# Request Model
# =========================

class ReviewRequest(BaseModel):
    id: int
    category: str
    reviewer: str


# =========================
# GET ARTICLE
# =========================

@app.get("/news/review")
def get_news(reviewer: str):

    conn = get_conn()
    cursor = conn.cursor()

    # 🔥 fetch unlocked article
    cursor.execute(f"""
        SELECT id, title, category, confidence
        FROM news
        WHERE confidence < 0.65
        AND reviewed = FALSE
        AND (
            locked_by IS NULL
            OR locked_at < NOW() - INTERVAL '{LOCK_TIMEOUT_MINUTES} minutes'
        )
        ORDER BY created_at DESC
        LIMIT 1
    """)

    row = cursor.fetchone()

    if not row:
        cursor.close()
        conn.close()

        return {
            "message": "No articles left"
        }

    news_id = row[0]

    # 🔒 lock article
    cursor.execute("""
        UPDATE news
        SET locked_by = %s,
            locked_at = NOW()
        WHERE id = %s
    """, (
        reviewer,
        news_id
    ))

    conn.commit()

    result = {
        "id": row[0],
        "title": row[1],
        "predicted": row[2],
        "confidence": row[3]
    }

    cursor.close()
    conn.close()

    return result


# =========================
# SUBMIT REVIEW
# =========================

@app.post("/news/review")
def review_news(data: ReviewRequest):

    conn = get_conn()
    cursor = conn.cursor()

    cursor.execute("""
        UPDATE news
        SET category = %s,
            reviewed = TRUE,
            locked_by = NULL,
            locked_at = NULL
        WHERE id = %s
    """, (
        data.category,
        data.id
    ))

    conn.commit()

    cursor.close()
    conn.close()

    return {
        "success": True,
        "message": "Review saved"
    }