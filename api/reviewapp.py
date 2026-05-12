from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from db import get_conn

app = FastAPI()

# =========================
# CORS FIX (IMPORTANT)
# =========================

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173"
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

LOCK_TIMEOUT_MINUTES = 10


# =========================
# REQUEST MODEL
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

    try:

        # 🔥 خطوة آمنة: اختيار + قفل في نفس العملية
        cursor.execute("""
            WITH next_article AS (
                SELECT id
                FROM news
                WHERE confidence < 0.65
                AND reviewed = FALSE
                AND (
                    locked_by IS NULL
                    OR locked_at < NOW() - INTERVAL '10 minutes'
                )
                ORDER BY created_at DESC
                LIMIT 1
            )
            UPDATE news n
            SET locked_by = %s,
                locked_at = NOW()
            FROM next_article
            WHERE n.id = next_article.id
            RETURNING n.id, n.title, n.category, n.confidence
        """, (reviewer,))

        row = cursor.fetchone()

        conn.commit()

        if not row:
            return {"message": "No articles left"}

        return {
            "id": row[0],
            "title": row[1],
            "predicted": row[2],
            "confidence": row[3]
        }

    finally:
        cursor.close()
        conn.close()


# =========================
# SUBMIT REVIEW
# =========================

@app.post("/news/review")
def review_news(data: ReviewRequest):

    conn = get_conn()
    cursor = conn.cursor()

    try:

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

        return {
            "success": True,
            "message": "Review saved"
        }

    finally:
        cursor.close()
        conn.close()
