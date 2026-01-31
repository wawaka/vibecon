"""Vibecon - Persistent Docker containers for AI coding assistants."""

__version__ = "2.0.0"
__author__ = "Vibecon Contributors"

from .cli import VibeconCLI

def main():
    """Entry point for the vibecon CLI."""
    cli = VibeconCLI()
    cli.run()

if __name__ == "__main__":
    main()