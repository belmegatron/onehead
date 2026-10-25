import logging
from logging import Filter, LogRecord
from socket import gaierror

from aiohttp.client_exceptions import ClientConnectorDNSError
from discord.utils import setup_logging as discord_setup_logging


# Name resolution failures, as raised by aiohttp and by the socket module beneath it.
DNS_ERRORS: tuple[type[BaseException], ...] = (ClientConnectorDNSError, gaierror)


def find_dns_error(exc: BaseException) -> BaseException | None:
    """
    Walk an exception chain looking for a name resolution failure.

    :param exc: The exception to inspect, along with anything it was raised from.
    :return: The name resolution failure, or None if the chain holds no such cause.
    """
    seen: set[int] = set()
    current: BaseException | None = exc

    while current is not None and id(current) not in seen:
        seen.add(id(current))

        if isinstance(current, DNS_ERRORS):
            return current

        current = current.__cause__ or current.__context__

    return None


def describe_dns_error(exc: BaseException) -> str:
    """
    Summarise a name resolution failure in a few words.

    :param exc: The name resolution failure.
    :return: A description naming the host we failed to resolve, where we know it.
    """
    if isinstance(exc, ClientConnectorDNSError):
        return f"DNS lookup for {exc.host}:{exc.port} failed - {exc.strerror}"

    return f"DNS lookup failed - {exc}"


class ConciseDNSErrorFilter(Filter):
    """
    Collapse name resolution tracebacks down to the line that precedes them.

    discord.py reconnects by itself when the gateway cannot be resolved, logging every
    attempt with Logger.exception(). The traceback is ~90 lines of aiohttp and asyncio
    internals that add nothing to the message above it, and a long outage repeats it
    until connectivity returns - 1253 lines in a day, when our DNS last went away. The
    reconnect attempt is still worth a line, so keep the message and append the cause
    in place of the traceback.
    """

    def filter(self, record: LogRecord) -> bool:
        if record.exc_info is None:
            return True

        exc: BaseException | None = record.exc_info[1]
        if exc is None:
            return True

        cause: BaseException | None = find_dns_error(exc)
        if cause is None:
            return True

        record.msg = f"{record.getMessage()} [{describe_dns_error(cause)}]"
        record.args = None
        record.exc_info = None
        record.exc_text = None  # A formatter may already have cached the traceback.

        return True


def setup_logging(level: int = logging.INFO) -> None:
    """
    Set up logging for discord.py, keeping DNS failures to a single line.

    :param level: The level to log at.
    """
    discord_setup_logging(level=level, root=True)

    # The records we want to rewrite are logged by discord.py's own loggers, so a filter
    # on our own logger would never see them. Filters on a parent logger do not apply to
    # records from its children either - only the handler they all share sees everything.
    dns_filter: ConciseDNSErrorFilter = ConciseDNSErrorFilter()
    for handler in logging.getLogger().handlers:
        handler.addFilter(dns_filter)
