import os

class FacebookPublisher:

    def __init__(self):


        self.page_id = os.getenv("FACEBOOK_PAGE_ID")
        self.token = os.getenv("FACEBOOK_ACCESS_TOKEN")

    def publish(self, post):
    message = f"""
📰 {post['title']}
{post.get('content', '')[:500]}
"""
    image_url = post.get("image_url")
    import requests

    url = f"https://graph.facebook.com/{self.page_id}/photos"
    payload = {
        "caption": message,
        "url": image_url,
        "access_token": self.token
    }

    response = requests.post(url, data=payload)
    
    if response.status_code == 200:
        print("✅ FACEBOOK POST SENT")
    else:
        print(f"❌ FACEBOOK ERROR: {response.status_code} - {response.text}")
