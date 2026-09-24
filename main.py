from core.bot import app
from core.loader import load_handlers


def main():
    load_handlers()
    print("Elara Bot starting...", flush=True)
    app.run()
    print("Elara Bot stopped.", flush=True)


if __name__ == "__main__":
    main()
