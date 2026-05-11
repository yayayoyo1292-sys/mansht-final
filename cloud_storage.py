import io
import os
from supabase import create_client

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)


def upload_image(image, filename):
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    buffer.seek(0)

    supabase.storage.from_("generated").upload(
        path=filename,
        file=buffer.read(),
        file_options={"content-type": "image/png"}
    )
