import asyncio
import gc
from unittest.mock import AsyncMock, MagicMock

import pytest
from discord.errors import ClientException

from onehead.common import (
    _background_tasks,
    create_background_task,
    play_sound,
    voice_client_disconnect,
)


class TestPlaySound:
    @pytest.mark.asyncio
    async def test_success(self, bot) -> None:
        def mock_play(_, *, after=None):
            if after:
                after(MagicMock())

        ctx = AsyncMock()
        ctx.voice_client.play = mock_play

        await play_sound(ctx, "start.mp3")

    @pytest.mark.asyncio
    async def test_ffmpeg_fails_to_play(self, bot) -> None:
        def mock_play(_, *, after=None):
            raise ClientException("oops!")

        ctx = AsyncMock()
        ctx.voice_client.play = mock_play

        await play_sound(ctx, "start.mp3")


class TestVoiceClientDisconnect:
    @pytest.mark.asyncio
    async def test_returns_when_there_is_no_voice_client(self) -> None:
        """
        play_sound skips playback when the caller is not in a voice channel, which used to
        leave this polling forever.
        """
        ctx = AsyncMock()
        ctx.voice_client = None

        await asyncio.wait_for(voice_client_disconnect(ctx), timeout=1)

    @pytest.mark.asyncio
    async def test_disconnects_once_playback_has_finished(self) -> None:
        ctx = AsyncMock()
        ctx.voice_client.is_playing = MagicMock(return_value=False)

        await asyncio.wait_for(voice_client_disconnect(ctx), timeout=1)

        ctx.voice_client.disconnect.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_gives_up_waiting_rather_than_polling_forever(self, monkeypatch) -> None:
        import onehead.common

        ctx = AsyncMock()
        ctx.voice_client.is_playing = MagicMock(return_value=True)

        monkeypatch.setattr(onehead.common, "MAX_PLAYBACK_WAIT_SECONDS", 0)

        await asyncio.wait_for(voice_client_disconnect(ctx), timeout=1)

        ctx.voice_client.disconnect.assert_awaited_once()


class TestCreateBackgroundTask:
    @pytest.mark.asyncio
    async def test_holds_a_reference_until_the_task_completes(self) -> None:
        started: asyncio.Event = asyncio.Event()

        async def work() -> None:
            started.set()
            await asyncio.sleep(0.05)

        task: asyncio.Task = create_background_task(work(), "work")
        await started.wait()

        # Dropping every local reference must not let the task be collected mid-flight.
        del task
        gc.collect()
        assert len(_background_tasks) == 1

        await asyncio.sleep(0.1)
        assert len(_background_tasks) == 0

    @pytest.mark.asyncio
    async def test_logs_the_exception_instead_of_swallowing_it(self, capsys) -> None:
        async def work() -> None:
            raise ValueError("boom")

        create_background_task(work(), "exploding_task")
        await asyncio.sleep(0.05)

        # structlog writes to stdout rather than through the stdlib handlers, so caplog
        # does not see this.
        output: str = capsys.readouterr().out
        assert "exploding_task" in output
        assert "boom" in output
        assert len(_background_tasks) == 0

    @pytest.mark.asyncio
    async def test_cancellation_is_not_reported_as_a_failure(self, capsys) -> None:
        async def work() -> None:
            await asyncio.sleep(10)

        task: asyncio.Task = create_background_task(work(), "cancelled_task")
        await asyncio.sleep(0)
        task.cancel()
        await asyncio.sleep(0.05)

        assert "cancelled_task" not in capsys.readouterr().out
