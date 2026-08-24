"""Minecraft Bedrock Realms monitoring.

This package currently contains only the authentication and Realms API client
(auth.py, realms_api.py, xbox_profile.py, models.py, exceptions.py, const.py),
used by the standalone proof-of-concept CLI in poc/realm_cli.py. Home Assistant
integration entry points (config_flow.py, coordinator.py, sensor.py, etc.) are
added in Phase 4 once the proof-of-concept confirms real Realm data can be
retrieved end-to-end.
"""
