import os
from db import get_conn

CATEGORIES = {
    "1": "رياضة",
    "2": "سياسة",
    "3": "فن",
    "4": "اجتماعية",
    "s": "skip"
}

REVIEWER = os.getenv("REVIEWER_NAME", "local-reviewer")

conn = get_conn()
cursor = conn.cursor()

# 🔹 هات الأخبار غير المراجعة وغير المقفولة
cursor.execute("""
    SELECT id, title, category, confidence
    FROM news
    WHERE confidence < 0.65
    AND reviewed = FALSE
    AND (
        locked_by IS NULL
        OR locked_at < NOW() - INTERVAL '10 minutes'
    )
    ORDER BY created_at DESC
    LIMIT 50
""")

rows = cursor.fetchall()

if not rows:
    print("✅ No articles to review")
    conn.close()
    exit()

reviewed = []

for news_id, title, predicted_cat, confidence in rows:

    # 🔒 lock article
    cursor.execute("""
        UPDATE news
        SET locked_by = %s,
            locked_at = NOW()
        WHERE id = %s
    """, (REVIEWER, news_id))

    conn.commit()

    os.system('cls' if os.name == 'nt' else 'clear')

    print("=" * 60)
    print(f"📰 {title}")
    print(f"🤖 Predicted: {predicted_cat} ({confidence:.2f})")
    print("=" * 60)
    print("1 → رياضة")
    print("2 → سياسة")
    print("3 → فن")
    print("4 → اجتماعية")
    print("s → skip")
    print("q → quit")
    print()

    choice = input("اختار: ").strip().lower()

    if choice == "q":
        break

    elif choice in CATEGORIES and choice != "s":

        correct_category = CATEGORIES[choice]

        cursor.execute("""
            UPDATE news
            SET category = %s,
                reviewed = TRUE,
                locked_by = NULL,
                locked_at = NULL
            WHERE id = %s
        """, (correct_category, news_id))

        reviewed.append((title, correct_category))

        print(f"✅ Saved as: {correct_category}")

    elif choice == "s":

        cursor.execute("""
            UPDATE news
            SET reviewed = TRUE,
                locked_by = NULL,
                locked_at = NULL
            WHERE id = %s
        """, (news_id,))

    conn.commit()

conn.close()

print(f"\n✅ Reviewed {len(reviewed)} articles")