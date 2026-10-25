import logging
from socket import gaierror

import pytest
from aiohttp.client_exceptions import ClientConnectorDNSError
from aiohttp.client_reqrep import ConnectionKey

from onehead.log import ConciseDNSErrorFilter, describe_dns_error, find_dns_error


def make_dns_error(host: str = "gateway-us-east1-b.discord.gg", port: int = 443) -> ClientConnectorDNSError:
    """
    Build the exception aiohttp raises when it cannot resolve the gateway.

    :param host: The host that failed to resolve.
    :param port: The port we tried to reach it on.
    :return: A name resolution failure chained onto the socket error that caused it.
    """
    cause: gaierror = gaierror(-3, "Temporary failure in name resolution")
    key: ConnectionKey = ConnectionKey(host, port, False, True, None, None, None)

    try:
        raise ClientConnectorDNSError(key, cause) from cause
    except ClientConnectorDNSError as exc:
        return exc


def make_record(exc: BaseException | None) -> logging.LogRecord:
    """
    Build the record discord.py emits from its reconnect loop.

    :param exc: The exception being logged, or None to log without one.
    :return: A log record carrying the exception.
    """
    return logging.LogRecord(
        name="discord.client",
        level=logging.ERROR,
        pathname="discord/client.py",
        lineno=781,
        msg="Attempting a reconnect in %.2fs",
        args=(358.83,),
        exc_info=None if exc is None else (type(exc), exc, exc.__traceback__),
    )


class TestFindDNSError:
    def test_finds_cause_through_chain(self) -> None:
        dns_error: ClientConnectorDNSError = make_dns_error()

        try:
            raise OSError("wrapped") from dns_error
        except OSError as exc:
            assert find_dns_error(exc) is dns_error

    def test_finds_bare_socket_error(self) -> None:
        cause: gaierror = gaierror(-3, "Temporary failure in name resolution")

        assert find_dns_error(cause) is cause

    def test_ignores_unrelated_errors(self) -> None:
        assert find_dns_error(ValueError("not a dns problem")) is None

    def test_survives_a_self_referential_chain(self) -> None:
        exc: ValueError = ValueError("loop")
        exc.__cause__ = exc

        assert find_dns_error(exc) is None


class TestDescribeDNSError:
    def test_names_the_host(self) -> None:
        summary: str = describe_dns_error(make_dns_error())

        assert summary == (
            "DNS lookup for gateway-us-east1-b.discord.gg:443 failed - Temporary failure in name resolution"
        )

    def test_falls_back_to_the_socket_error(self) -> None:
        cause: gaierror = gaierror(-3, "Temporary failure in name resolution")

        assert describe_dns_error(cause) == "DNS lookup failed - [Errno -3] Temporary failure in name resolution"


class TestConciseDNSErrorFilter:
    @pytest.fixture
    def dns_filter(self) -> ConciseDNSErrorFilter:
        return ConciseDNSErrorFilter()

    def test_replaces_traceback_with_a_summary(self, dns_filter: ConciseDNSErrorFilter) -> None:
        record: logging.LogRecord = make_record(make_dns_error())

        assert dns_filter.filter(record) is True
        assert record.exc_info is None
        assert record.exc_text is None
        assert record.getMessage() == (
            "Attempting a reconnect in 358.83s [DNS lookup for gateway-us-east1-b.discord.gg:443 failed"
            " - Temporary failure in name resolution]"
        )

    def test_formats_to_a_single_line(self, dns_filter: ConciseDNSErrorFilter) -> None:
        record: logging.LogRecord = make_record(make_dns_error())
        dns_filter.filter(record)

        formatted: str = logging.Formatter("{levelname} {name} {message}", style="{").format(record)

        assert "\n" not in formatted
        assert "Traceback" not in formatted

    def test_leaves_other_tracebacks_alone(self, dns_filter: ConciseDNSErrorFilter) -> None:
        try:
            raise ValueError("something we do want to see")
        except ValueError as exc:
            record: logging.LogRecord = make_record(exc)

        assert dns_filter.filter(record) is True
        assert record.exc_info is not None
        assert record.getMessage() == "Attempting a reconnect in 358.83s"

    def test_leaves_records_without_an_exception_alone(self, dns_filter: ConciseDNSErrorFilter) -> None:
        record: logging.LogRecord = make_record(None)

        assert dns_filter.filter(record) is True
        assert record.getMessage() == "Attempting a reconnect in 358.83s"
