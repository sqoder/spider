"""
Account repository — CRUD operations for the account_pool table.
Handles retrieving healthy accounts and marking rate limits.
"""

from datetime import UTC, datetime
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.account import Account
from app.schemas.account import AccountCreate, AccountUpdate


class AccountRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create(self, data: AccountCreate) -> Account:
        """Create a new account in the pool."""
        account = Account(**data.model_dump())
        self.db.add(account)
        await self.db.commit()
        await self.db.refresh(account)
        return account

    async def get_healthy_account(self, platform: str) -> Account | None:
        """
        Get a random, active, non-rate-limited account for the given platform.
        Updates the last_used_at timestamp.
        """
        # First, check if any rate_limited_until times have expired, and un-limit them
        now = datetime.now(UTC)
        stmt_reset = (
            update(Account)
            .where(
                Account.platform == platform,
                Account.is_rate_limited == True,
                Account.rate_limited_until != None,
                Account.rate_limited_until <= now,
            )
            .values(is_rate_limited=False, rate_limited_until=None)
        )
        await self.db.execute(stmt_reset)

        # Now get a healthy account, ordered by least recently used to round-robin
        # Or random func.random() but least recently used is more stable
        stmt_get = (
            select(Account)
            .where(
                Account.platform == platform,
                Account.is_active == True,
                Account.is_rate_limited == False,
            )
            .order_by(Account.last_used_at.asc().nullsfirst())
            .limit(1)
        )
        
        result = await self.db.execute(stmt_get)
        account = result.scalar_one_or_none()
        
        if account:
            account.last_used_at = now
            await self.db.commit()
            await self.db.refresh(account)
            
        return account

    async def mark_rate_limited(self, account_id: int, cooldown_seconds: int = 3600) -> bool:
        """Mark an account as rate limited for a specific duration."""
        account = await self.db.get(Account, account_id)
        if not account:
            return False
            
        account.is_rate_limited = True
        account.rate_limited_until = datetime.now(UTC).timestamp() + cooldown_seconds
        # we will store it as a proper datetime
        from datetime import timedelta
        account.rate_limited_until = datetime.now(UTC) + timedelta(seconds=cooldown_seconds)
        
        await self.db.commit()
        return True

    async def mark_failed(self, account_id: int, max_errors: int = 3) -> bool:
        """Increment error count, disable if it exceeds max_errors."""
        account = await self.db.get(Account, account_id)
        if not account:
            return False
            
        account.error_count += 1
        if account.error_count >= max_errors:
            account.is_active = False
            
        await self.db.commit()
        return True

    async def list_accounts(
        self, platform: str | None = None, limit: int = 50, offset: int = 0
    ) -> tuple[list[Account], int]:
        query = select(Account)
        count_query = select(func.count(Account.id))

        if platform:
            query = query.where(Account.platform == platform)
            count_query = count_query.where(Account.platform == platform)

        total = (await self.db.execute(count_query)).scalar() or 0
        query = query.order_by(Account.id.desc()).offset(offset).limit(limit)
        result = await self.db.execute(query)
        
        return list(result.scalars().all()), total
