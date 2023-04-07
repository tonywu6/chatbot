import asyncio
from contextlib import suppress

import click
import watchfiles

from dougbot3.bot import create_bot
from dougbot3.settings import AppSecrets

SECRETS = AppSecrets()


@click.group()
def cli():
    pass


async def _main():
    async with await create_bot() as bot:
        await bot.start(SECRETS.get_bot_token())


def main():
    with suppress(KeyboardInterrupt):
        asyncio.run(_main())


@cli.command()
@click.option("--autoreload", is_flag=True, default=False, help="Enable auto-reload.")
def start(autoreload: bool = False):
    if autoreload:
        watchfiles.run_process(".", target=main)
    else:
        main()


@cli.command()
async def sync_commands():
    async with await create_bot() as bot:
        await bot.login(SECRETS.get_bot_token())
        await bot.tree.sync()


if __name__ == "__main__":
    cli()
