from db import get_conn

conn = get_conn()

# مهم: تشغيل autocommit للأوامر DDL
conn.autocommit = True

cursor = conn.cursor()

# =========================
# NEWS TABLE
# =========================

cursor.execute("""
CREATE TABLE IF NOT EXISTS news (
    id SERIAL PRIMARY KEY,
    title TEXT UNIQUE,
    url TEXT UNIQUE,
    image TEXT,
    category TEXT,
    confidence REAL,
    content TEXT,
    reviewed BOOLEAN DEFAULT FALSE,
    locked_by TEXT,
    locked_at TIMESTAMP,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
""")

# =========================
# TRAINING TABLE
# =========================

cursor.execute("""
CREATE TABLE IF NOT EXISTS confirmed_training (
    id SERIAL PRIMARY KEY,
    title TEXT UNIQUE,
    category TEXT,
    confidence REAL,
    source TEXT DEFAULT 'auto',
    created_at TIMESTAMPTZ DEFAULT NOW()
);
""")

# =========================
# INDEXES (مهم جدًا للأداء)
# =========================

cursor.execute("""
CREATE INDEX IF NOT EXISTS idx_news_reviewed
ON news(reviewed);
""")

cursor.execute("""
CREATE INDEX IF NOT EXISTS idx_news_confidence
ON news(confidence);
""")

cursor.execute("""
CREATE INDEX IF NOT EXISTS idx_news_created_at
ON news(created_at DESC);
""")

cursor.close()
conn.close()

print("✅ Tables + indexes created successfully")