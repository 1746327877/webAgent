import asyncio

from sqlalchemy import select

from app.core.db import SessionLocal
from app.core.security import hash_password
from app.models.user import User


async def main() -> None:
    async with SessionLocal() as db:
        exists = await db.scalar(select(User).where(User.username == "demo"))
        if exists:
            print("demo 用户已存在，跳过")
            return
        db.add(
            User(
                username="demo",
                email="demo@example.com",
                password_hash=hash_password("Demo123456"),
                display_name="演示用户",
                role="admin",
            )
        )
        await db.commit()
        print("已创建演示账号：demo / Demo123456")


if __name__ == "__main__":
    asyncio.run(main())
