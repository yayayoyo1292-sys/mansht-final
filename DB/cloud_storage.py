import io
import os
from supabase import create_client

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

supabase = create_client(
    SUPABASE_URL,
    SUPABASE_KEY
)


def upload_image(image, filename):

    # JPEG doesn't support alpha
    image = image.convert("RGB")

    # force jpg extension
    filename = filename.replace(".png", ".jpg")

    buffer = io.BytesIO()

    image.save(
        buffer,
        format="JPEG",
        quality=85,
        optimize=True
    )

    buffer.seek(0)

    size_mb = len(buffer.getvalue()) / (1024 * 1024)

    print(f"🖼️ Uploading image: {size_mb:.2f} MB")

    result = supabase.storage.from_("generated").upload(
        path=filename,
        file=buffer.read(),
        file_options={
            "content-type": "image/jpeg"
        }
    )

    print("✅ Upload Result:", result)