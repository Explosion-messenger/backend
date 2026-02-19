import asyncio
from sqlalchemy import update
from app.database import AsyncSessionLocal
from app.models import User

async def make_admin(username: str):
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            update(User).where(User.username == username).values(is_admin=True)
        )
        await session.commit()
        if result.rowcount > 0:
            print(f"User {username} is now an admin.")
        else:
            print(f"User {username} not found.")

if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Usage: python set_admin.py <username>")
    else:
        asyncio.run(make_admin(sys.argv[1]))
