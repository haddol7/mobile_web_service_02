#!/usr/bin/env python
"""Run Django commands from the mounted Windows tree in WSL."""
import os
import sys


def main():
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "photoblog.settings")
    from django.core.management import execute_from_command_line
    execute_from_command_line(sys.argv)


if __name__ == "__main__":
    main()
