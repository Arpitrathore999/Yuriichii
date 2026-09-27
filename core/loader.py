def load_handlers():
    # Core bot handlers
    import handlers.start
    import handlers.ai
    import handlers.social
    import handlers.admin
    import handlers.ping
    import handlers.broadcast

    # GC Management System
    import management.bans
    import management.warnings
    import management.purge
    import management.pin
    import management.lock
    import management.greetings
    import management.report
    import management.filter
