"""Legacy launcher retained for compatibility; it now opens the graphical client."""

from client.client import main


if __name__ == "__main__":
    raise SystemExit(main())
