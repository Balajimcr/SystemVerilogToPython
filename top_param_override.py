#!/usr/bin/env python3
"""
Backward-compatibility wrapper for param_override.
===================================================

This module re-exports everything from ``param_override``.
New code should import from ``param_override`` directly.
"""
from param_override import *  # noqa: F401,F403
from param_override import _cli_main  # noqa: F401

if __name__ == "__main__":
    _cli_main()
