"""Minimal import smoke tests for the nanobot package."""

from __future__ import annotations


def test_nanobot_package_importable() -> None:
    import nanobot  # noqa: F401

    assert nanobot.__doc__ is None or isinstance(nanobot.__doc__, str)


def test_cli_app_exists() -> None:
    import typer

    from nanobot.cli.commands import app

    assert isinstance(app, typer.Typer)
