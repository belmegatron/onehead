import asyncio
import logging

from discord.ext.commands import Bot
from structlog import get_logger

from onehead.config import Config, load_config
from onehead.core import bot_builder
from onehead.log import setup_logging

log: logging.Logger = get_logger()


async def main() -> None:
    setup_logging(level=logging.INFO)

    config: Config = load_config()
    bot: Bot = await bot_builder(config)

    await bot.start(config.discord.token)


if __name__ == "__main__":
    asyncio.run(main())
