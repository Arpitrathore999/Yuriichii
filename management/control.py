"""Elara GC Management - Admin/Control bridge.

The main owner/admin panel lives in ``handlers.admin``.  This module is kept
as a separate Management module so the Help -> Management -> Admin section
can map to the existing admin commands without registering duplicate handlers.
"""

# Admin commands are registered by handlers.admin.
# Keeping this module intentionally handler-free prevents duplicate command
# registration and callback/global-handler conflicts.

MANAGEMENT_ADMIN_COMMANDS = (
    "/promote", "/demote", "/adminlist", "/adminpanel", "/adminuser",
    "/banbot", "/botunban", "/stats", "/broadcast",
)
