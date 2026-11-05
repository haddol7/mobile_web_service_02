"""Use the same private production configuration for Django management commands."""
import argparse
import os
from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))
from deploy.production import load_environment


def main():
    parser = argparse.ArgumentParser(description=__doc__, add_help=False)
    parser.add_argument("--config", required=True)
    arguments, management_arguments = parser.parse_known_args()
    if not management_arguments:
        parser.error("Supply a Django management command, for example check --deploy.")
    load_environment(arguments.config, PROJECT_ROOT)
    os.chdir(PROJECT_ROOT)
    from django.core.management import execute_from_command_line
    execute_from_command_line([str(PROJECT_ROOT / "manage.py"), *management_arguments])


if __name__ == "__main__":
    main()
