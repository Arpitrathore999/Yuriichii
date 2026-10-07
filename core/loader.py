def load_handlers():
    """Load all bot modules without allowing one optional module to kill startup."""
    modules = [
        "handlers.start", "handlers.ai", "handlers.social", "handlers.economy",
        "handlers.admin", "handlers.ping", "handlers.broadcast",
        "management.control", "management.bans", "management.filter",
        "management.greetings", "management.lock", "management.pin",
        "management.purge", "management.report", "management.warnings", "management.tagall",
        "handlers.cardgame", "handlers.hackgame", "handlers.ttt", "handlers.id", "handlers.quote"
        "handlers.logger",
    ]
    for module_name in modules:
        try:
            __import__(module_name)
            print(f"[LOADER] loaded: {module_name}", flush=True)
        except Exception as exc:
            print(f"[LOADER] FAILED: {module_name}: {type(exc).__name__}: {exc}", flush=True)
