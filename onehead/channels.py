from asyncio import gather
from logging import Logger

from discord import VoiceChannel
from discord.errors import HTTPException
from discord.ext.commands import Cog, Context
from discord.guild import Guild
from discord.member import Member
from structlog import get_logger

from onehead.common import OneHeadException
from onehead.config import Config, DiscordChannelConfig
from onehead.store import GameStore

log: Logger = get_logger()


async def move_member(member: Member, channel: VoiceChannel) -> None:
    """
    Move one member into a voice channel, reporting a refusal rather than raising.

    Keeping the failure local means one member who cannot be moved does not abandon
    the rest, which matters now that the moves are issued together.

    :param member: The member to move.
    :param channel: The channel to move them to.
    """
    try:
        await member.move_to(channel)
    except HTTPException as ex:
        log.error(f"Failed to move {member.display_name} to {channel.name} due to {ex}.")


class Channels(Cog):
    def __init__(self, store: GameStore, config: Config) -> None:
        self.store: GameStore = store
        channel_config_settings: DiscordChannelConfig = config.discord.channels
        self.channel_names: list[str] = [f"{channel_config_settings.match} #{x}" for x in (1, 2)]
        self.lobby_name: str = channel_config_settings.lobby
        self.ihl_discord_channels: list[VoiceChannel]

    async def create_discord_channels(self, ctx: Context) -> None:
        """
        We check if the channels already exist, if not we create them.

        :param ctx: Discord Context
        """
        guild: Guild | None = ctx.guild
        if guild is None:
            raise OneHeadException("No Guild associated with Discord Context")

        expected_ihl_channels: list[str] = [x.name for x in guild.voice_channels if x.name in self.channel_names]

        for channel in self.channel_names:
            if channel not in expected_ihl_channels:
                await ctx.send(f"Creating {channel} channel")
                await guild.create_voice_channel(channel)

        self.ihl_discord_channels = [x for x in guild.voice_channels if x.name in self.channel_names]

    async def move_back_to_lobby(self, ctx: Context, members: tuple[list[Member], list[Member]]) -> None:
        """
        Move players back from IHL Team Channels to a communal channel.

        :param ctx: Discord Context
        """
        guild: Guild | None = ctx.guild
        if guild is None:
            raise OneHeadException("No Guild associated with Discord Context")

        selected_channels: list[VoiceChannel] = [x for x in guild.voice_channels if x.name == self.lobby_name]
        if len(selected_channels) != 1:
            raise OneHeadException("Failed to find lobby voice channel")

        lobby: VoiceChannel = selected_channels[0]

        await gather(*(move_member(player, lobby) for team in members for player in team))

    async def move_discord_channels(self, ctx: Context, members: tuple[list[Member], list[Member]]) -> None:
        """
        Move players to IHL Team Channels.

        :param ctx: Discord Context
        """
        channel_count: int = len(self.ihl_discord_channels)
        if channel_count != 2:
            raise OneHeadException(f"Expected 2 Discord Channels, Identified {channel_count}.")

        await ctx.send("Moving players to channels...")

        t1_discord_members: list[Member]
        t2_discord_members: list[Member]

        t1_discord_members, t2_discord_members = members

        t1_channel: VoiceChannel
        t2_channel: VoiceChannel

        t1_channel, t2_channel = self.ihl_discord_channels

        await gather(
            *(
                move_member(member, channel)
                for team, channel in ((t1_discord_members, t1_channel), (t2_discord_members, t2_channel))
                for member in team
            )
        )
