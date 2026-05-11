import json
import re
import pandas as pd
import joblib

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import train_test_split
from sklearn.metrics import classification_report, accuracy_score

from db import get_conn

# =========================
# ARABIC STOPWORDS
# =========================

arabic_stopwords = set([
    "في", "من", "الى", "على", "عن", "مع", "هذا", "هذه",
    "هو", "هي", "كان", "تم", "ما", "لا", "لم", "لن",
    "كل", "قد", "وقد", "و", "او", "أو", "ان", "إن"
])

# =========================
# ARABIC NORMALIZATION
# =========================

def normalize_arabic(text):
    text = str(text)
    text = re.sub(r"[إأآا]", "ا", text)
    text = re.sub(r"ى", "ي", text)
    text = re.sub(r"ؤ", "و", text)
    text = re.sub(r"ئ", "ي", text)
    text = re.sub(r"ة", "ه", text)
    text = re.sub(r"[^\w\s]", " ", text)
    text = re.sub(r"\d+", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()

# =========================
# LOAD FROM DATABASE (POSTGRES)
# =========================

def load_from_database(min_confidence=0.50):

    try:

        conn = get_conn()
        cur = conn.cursor()

        # =====================
        # NEWS TABLE
        # =====================

        cur.execute("""
            SELECT title, category, confidence
            FROM news
            WHERE confidence >= %s
            AND category != 'عام'
            AND title IS NOT NULL
        """, (min_confidence,))

        news_rows = cur.fetchall()

        # =====================
        # CONFIRMED TRAINING
        # =====================

        cur.execute("""
            SELECT title, category, confidence
            FROM confirmed_training
            WHERE title IS NOT NULL
        """)

        confirmed_rows = cur.fetchall()

        conn.close()

        # =====================
        # MERGE DATA
        # =====================

        db_data = []
        seen = set()

        for title, category, confidence in confirmed_rows + news_rows:

            if title and category and title not in seen:

                seen.add(title)

                db_data.append((title.strip(), category))

        print(f"  - From news table: {len(news_rows)}")
        print(f"  - From confirmed table: {len(confirmed_rows)}")

        return db_data

    except Exception as e:

        print(f"⚠️ Could not load from database: {e}")

        return []

# =========================
# LOAD DATASET
# =========================

with open("dataset.json", "r", encoding="utf-8") as f:
    data = json.load(f)

print(f"📁 Base dataset: {len(data)} examples")

db_data = load_from_database(min_confidence=0.50)

print(f"🗄️ Database data: {len(db_data)} examples")

all_data = data + db_data

print(f"📊 Total combined: {len(all_data)} examples")

df = pd.DataFrame(all_data, columns=["text", "label"])

# =========================
# CLEAN TEXT
# =========================

df["text"] = df["text"].apply(normalize_arabic)

print("\n=========================")
print("DATASET INFO")
print("=========================")

print("DATASET SIZE:", len(df))
print("\nLABEL COUNTS:\n")
print(df["label"].value_counts())

# =========================
# SPLIT
# =========================

X_train_text, X_test_text, y_train, y_test = train_test_split(
    df["text"],
    df["label"],
    test_size=0.25,
    random_state=42,
    stratify=df["label"]
)

# =========================
# TF-IDF
# =========================

vectorizer = TfidfVectorizer(
    analyzer="word",
    ngram_range=(1, 2),
    max_features=2000,
    min_df=2,
    max_df=0.80,
    stop_words=list(arabic_stopwords),
    sublinear_tf=True
)

X_train = vectorizer.fit_transform(X_train_text)
X_test = vectorizer.transform(X_test_text)

# =========================
# MODEL
# =========================

model = LogisticRegression(
    max_iter=3000,
    C=0.3,
    class_weight="balanced",
    solver="saga",
    tol=1e-4
)

# =========================
# TRAIN
# =========================

print("\n=========================")
print("TRAINING MODEL...")
print("=========================\n")

model.fit(X_train, y_train)

# =========================
# PREDICTIONS
# =========================

predictions = model.predict(X_test)

# =========================
# EVALUATION
# =========================

accuracy = accuracy_score(y_test, predictions)

print("\n=========================")
print("MODEL ACCURACY")
print("=========================")
print(f"\nAccuracy: {accuracy:.2f}")

print("\nTRAIN SCORE:", model.score(X_train, y_train))
print("TEST SCORE :", model.score(X_test, y_test))

print("\n=========================")
print("CLASSIFICATION REPORT")
print("=========================\n")

print(classification_report(y_test, predictions))

# =========================
# SAVE MODEL
# =========================

joblib.dump(model, "model.pkl")
joblib.dump(vectorizer, "vectorizer.pkl")

print("\n=========================")
print("MODEL SAVED")
print("=========================")

print("\n🚀 TRAINING COMPLETED SUCCESSFULLY")