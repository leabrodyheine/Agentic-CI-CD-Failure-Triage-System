import logging

from triage_agent.logging_config import configure_logging


def _reset_root_logger():
    root = logging.getLogger()
    for handler in list(root.handlers):
        root.removeHandler(handler)
    root.setLevel(logging.WARNING)


def test_configure_logging_sets_level():
    _reset_root_logger()

    configure_logging("DEBUG")

    assert logging.getLogger().level == logging.DEBUG


def test_configure_logging_adds_one_handler():
    _reset_root_logger()

    configure_logging("INFO")
    configure_logging("INFO")

    assert len(logging.getLogger().handlers) == 1


def test_configure_logging_falls_back_to_info_for_invalid_level():
    _reset_root_logger()

    configure_logging("not-a-real-level")

    assert logging.getLogger().level == logging.INFO


def test_configure_logging_is_case_insensitive():
    _reset_root_logger()

    configure_logging("warning")

    assert logging.getLogger().level == logging.WARNING
