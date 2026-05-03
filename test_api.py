import asyncio

from httpx import ASGITransport, AsyncClient

from app.main import app


async def test_insert_and_get():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        data = {
            "platform": "youtube",
            "source_id": "test_video_001",
            "url": "https://www.youtube.com/watch?v=test",
            "title": "Test YouTube Video",
            "content": "This is a test video.",
            "post_type": "video",
            "like_count": 100,
            "comment_count": 10,
            "share_count": 0,
            "view_count": 1000,
            "raw_data": {"test": True},
        }
        # Post the data
        print("Creating post...")
        response = await ac.post("/api/posts", json=data)
        print("POST status:", response.status_code)
        print("POST response:", response.json())

        # Get the data
        print("\nListing posts...")
        response = await ac.get("/api/posts")
        print("GET status:", response.status_code)
        print("GET response:", response.json())


if __name__ == "__main__":
    asyncio.run(test_insert_and_get())
