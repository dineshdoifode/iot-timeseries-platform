from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import Role, User


class UserRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_username(self, username: str) -> User | None:
        result = await self.session.execute(select(User).where(User.username == username))
        return result.scalar_one_or_none()

    async def get_role_name(self, role_id: int) -> str | None:
        result = await self.session.execute(select(Role.name).where(Role.id == role_id))
        return result.scalar_one_or_none()

    async def get_role_id(self, role_name: str) -> int | None:
        result = await self.session.execute(select(Role.id).where(Role.name == role_name))
        return result.scalar_one_or_none()

    async def create(self, username: str, email: str, hashed_password: str, role_name: str) -> User:
        role_id = await self.get_role_id(role_name)
        user = User(
            username=username,
            email=email,
            hashed_password=hashed_password,
            role_id=role_id,
            is_active=True,
            created_at=datetime.now(timezone.utc),
        )
        self.session.add(user)
        await self.session.commit()
        await self.session.refresh(user)
        return user
