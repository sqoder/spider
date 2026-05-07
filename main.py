import asyncio
from app.core.runner import run_with_config

def main():
    try:
        asyncio.run(run_with_config())
    except RuntimeError:
        loop = asyncio.get_event_loop()
        if not loop.is_running():
            loop.run_until_complete(run_with_config())

if __name__ == "__main__":
    main()
