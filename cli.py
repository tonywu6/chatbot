import asyncio
from contextlib import suppress

import click
from loguru import logger

from chatbot.bot import create_bot
from chatbot.settings import AppSecrets
from chatbot.utils.config import load_settings
from chatbot.utils.logging import configure_logging


@click.group()
@click.option("--debug", is_flag=True, default=False)
@click.option("--log-file", type=click.File("a+"), default=None)
def cli(debug: bool = False, log_file: str | None = None):
    configure_logging(log_file, level="DEBUG" if debug else "INFO")


@cli.command()
@click.option("--autoreload", is_flag=True, default=False, help="Enable auto-reload.")
def run(autoreload: bool = False):
    if autoreload:
        import watchfiles

        watch_filter = watchfiles.PythonFilter(
            extra_extensions=[".tmp"],
            ignore_paths=["instance"],
        )

        def on_change(*args, **kwargs):
            logger.warning("File changes detected. Restarting...")

        watchfiles.run_process(
            ".",
            target=f"python {__file__} run",
            callback=on_change,
            watch_filter=watch_filter,
        )

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
    SECRETS = load_settings(AppSecrets)
    cli()
