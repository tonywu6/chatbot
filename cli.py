import asyncio
import shlex
import sys
from contextlib import suppress

import click
from chatbot.bot import create_bot
from chatbot.settings import AppSecrets
from chatbot.utils.config import load_settings, set_profile
from chatbot.utils.logging import configure_logging
from loguru import logger


@click.group()
@click.option("-p", "--profile", default=None)
@click.option("--debug", is_flag=True, default=False)
@click.option("--log-file", type=click.File("a+"), default=None)
def cli(profile: str | None = None, debug: bool = False, log_file: str | None = None):
    set_profile(profile)
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

        args = sys.argv[:]
        args.remove("--autoreload")

        watchfiles.run_process(
            ".",
            target=shlex.join([sys.executable, *args]),
            callback=on_change,
            watch_filter=watch_filter,
        )

        return

    async def main():
        bot = await create_bot()
        async with bot:
            await bot.start(load_settings(AppSecrets).get_bot_token())

    with suppress(KeyboardInterrupt):
        asyncio.run(main())


@cli.command()
def sync_commands():
    async def main():
        bot = await create_bot()
        async with bot:
            await bot.login(load_settings(AppSecrets).get_bot_token())
            await bot.tree.sync()

    asyncio.run(main())


if __name__ == "__main__":
    cli()
