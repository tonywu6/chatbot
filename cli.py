import asyncio
from contextlib import suppress

import click
import watchfiles
from loguru import logger

from dougbot3.bot import create_bot
from dougbot3.settings import AppSecrets
from dougbot3.utils.logging import configure_logging

SECRETS = AppSecrets()


@click.group()
@click.option("--debug", is_flag=True, default=False)
@click.option("--log-file", type=click.File("a+"), default=None)
def cli(debug: bool = False, log_file: str | None = None):
    configure_logging(log_file, level="DEBUG" if debug else "INFO")


@cli.command()
@click.option("--autoreload", is_flag=True, default=False, help="Enable auto-reload.")
def run(autoreload: bool = False):
    if autoreload:

        def on_change(*args, **kwargs):
            logger.warning("File changes detected. Restarting...")

        watchfiles.run_process(".", target=f"python {__file__} run", callback=on_change)

        return

    async def main():
        bot = await create_bot()
        async with bot:
            await bot.start(SECRETS.get_bot_token())

    with suppress(KeyboardInterrupt):
        asyncio.run(main())


@cli.command()
def sync_commands():
    async def main():
        bot = await create_bot()
        async with bot:
            await bot.login(SECRETS.get_bot_token())
            await bot.tree.sync()

    asyncio.run(main())


if __name__ == "__main__":
    cli()