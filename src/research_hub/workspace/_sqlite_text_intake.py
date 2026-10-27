"""Private prototype entry point only; deliberately absent from all public routes.

Tests/new synthetic workspaces only. No native-publication fallback, user DB
migration, feature advertisement, backup, export, permission change or auto Run.
"""
from .text_intake import TextIntake


class SQLiteTextIntake(TextIntake):
    _blob_storage = True

    def _check_capability(self):
        # Explicit internal class selection, never retry/fallback from file errors.
        pass
