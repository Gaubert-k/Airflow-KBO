"""Smoke tests MS-00 — imports packages sans Airflow."""

from packages.platform.logging import configure_structured_logging


def test_packages_version() -> None:
    import packages

    assert packages.__version__ == "0.1.0"


def test_structured_logging_configures() -> None:
    configure_structured_logging()
    import logging

    logging.getLogger("test").info("smoke")
