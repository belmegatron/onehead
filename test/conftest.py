import random
from collections.abc import AsyncGenerator, Sequence
from pathlib import Path

import discord.ext.test as dpytest
import pytest_asyncio
from discord.ext.commands import Bot
from discord.guild import Guild
from discord.member import Member
from discord.role import Role

from onehead.common import Player, Team
from onehead.config import Config, TinyDBConfig, DiscordChannelConfig, DiscordConfig
from onehead.core import bot_builder

TEST_USER: str = "TestUser0_0_nick"


@pytest_asyncio.fixture
async def bot() -> Bot:
    config: Config = Config(
        tinydb=TinyDBConfig(Path(__file__).parent / "test_db.json"),
        discord=DiscordConfig("token", DiscordChannelConfig("lobby", "match")),
    )
    bot: Bot = await bot_builder(config)
    await bot._async_setup_hook()
    dpytest.configure(bot)

    # Create the roles that are used by OneHead.
    guilds: Sequence[Guild] = bot.guilds
    guild: Guild = guilds[0]
    await guild.create_role(name="IHL")
    await guild.create_role(name="IHL Admin")
    return bot


@pytest_asyncio.fixture(autouse=True)
async def cleanup() -> AsyncGenerator[None, None]:
    await dpytest.empty_queue()
    yield


async def add_ihl_role(bot: Bot, role: str, name: str | None = None) -> None:
    guilds: Sequence[Guild] = bot.guilds
    guild: Guild = guilds[0]
    members: list[Member] = list(bot.get_all_members())

    if name is not None:
        target_member: Member = [member for member in members if member.name == name][0]
    else:
        target_member = members[0]

    roles: Sequence[Role] = guild.roles
    ihl_role: Role = [x for x in roles if x.name == role][0]
    await dpytest.add_role(target_member, ihl_role)


async def join_member(bot: Bot, name: str) -> Member:
    """
    Add a member to the test guild and hand them back.

    Needed before building a team that is meant to contain them, as a player record
    carries the member's Discord id.

    :param bot: The bot under test.
    :param name: The member's account name.
    :return: The member.
    """
    await dpytest.member_join(name=name)

    return [member for member in bot.get_all_members() if member.name == name][0]


def get_test_member(bot: Bot) -> Member:
    """
    The member that dpytest sends messages as.

    :param bot: The bot under test.
    :return: The member.
    """
    return list(bot.get_all_members())[0]


def create_test_player(bot: Bot) -> Player:
    """
    Build a player record for the member dpytest sends messages as.

    A player's id is their Discord id, so a record standing in for a real participant
    has to carry the member's id rather than a placeholder.

    :param bot: The bot under test.
    :return: The player.
    """
    return Player(id=get_test_member(bot).id, name=TEST_USER, mmr=3000)


def create_fake_player() -> Player:
    id: int = random.randint(0, 99999)
    name: str = f"user_{id}"
    mmr: int = random.randint(0, 9000)
    return Player(id=id, name=name, mmr=mmr)


def create_fake_team() -> Team:
    return (
        create_fake_player(),
        create_fake_player(),
        create_fake_player(),
        create_fake_player(),
        create_fake_player(),
    )
