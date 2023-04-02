import asyncio
from contextlib import suppress

import click


@click.group()
def cli():
    pass


@cli.command()
def start():
    from .bot import create_bot
    from .settings import AppSecrets

    secrets = AppSecrets()

    async def main():
        bot = await create_bot()
        async with bot:
            await bot.start(secrets.get_bot_token())

    with suppress(KeyboardInterrupt):
        asyncio.run(main())


@cli.command()
def sync_commands():
    from .bot import create_bot
    from .settings import AppSecrets

    secrets = AppSecrets()

    async def main():
        bot = await create_bot()
        async with bot:
            await bot.login(secrets.get_bot_token())
            await bot.tree.sync()

    asyncio.run(main())


if __name__ == "__main__":
    cli()
