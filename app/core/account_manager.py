"""
Account Manager — orchestrates the dummy account and cookie pool.
Handles fetching active cookies to bypass Login Walls on X and Instagram.
"""

from loguru import logger

from app.db.session import get_session_factory
from app.repositories.account_repo import AccountRepository


class AccountManager:
    def __init__(self):
        self.session_factory = get_session_factory()

    async def get_healthy_cookie_for_platform(self, platform: str) -> dict | None:
        """
        Get a healthy cookie/token for the platform.
        Returns a dict with 'auth_token' or 'cookies_data', or None if pool empty.
        """
        async with self.session_factory() as session:
            repo = AccountRepository(session)
            account = await repo.get_healthy_account(platform)
            
            if not account:
                logger.warning(f"No healthy accounts available in pool for {platform}!")
                return None
                
            logger.info(f"AccountManager: Selected healthy account '{account.username}' for {platform}")
            
            # Format the return value depending on what is stored
            return {
                "account_id": account.id,
                "username": account.username,
                "auth_token": account.auth_token,
                "cookies_data": account.cookies_data,
            }

    async def report_account_rate_limited(self, account_id: int, cooldown_seconds: int = 3600):
        """Report that an account hit a rate limit (e.g. 429 Too Many Requests)."""
        async with self.session_factory() as session:
            repo = AccountRepository(session)
            await repo.mark_rate_limited(account_id, cooldown_seconds)
            logger.warning(f"Account {account_id} marked as rate-limited for {cooldown_seconds}s")

    async def report_account_failed(self, account_id: int):
        """Report that an account completely failed (e.g. checkpoint/banned)."""
        async with self.session_factory() as session:
            repo = AccountRepository(session)
            await repo.mark_failed(account_id)
            logger.warning(f"Account {account_id} reported a hard failure. Error count incremented.")


account_manager = AccountManager()
