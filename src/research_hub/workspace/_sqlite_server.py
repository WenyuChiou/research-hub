"""Private synthetic integration admission, not a CLI/env/HTTP feature selector.

Only direct Python construction selects this experimental service/server instance.
Public constructors retain file-backed defaults. No fallback from denied native
operations, migration, browser launch, auto Run, or storage capability promotion.
"""
from .service import WorkspaceService
from .server import WorkspaceServer
from ._sqlite_text_intake import SQLiteTextIntake
from .research_draft import MAX_SOURCE_BYTES


class SQLiteWorkspaceService(WorkspaceService):
    def _text_intake(self):
        return SQLiteTextIntake(self.workspace)

    def _text_intake_capability(self):
        namespace = self.workspace.preparation_namespace()
        return {'version': 1, 'status': 'available' if namespace else 'unavailable',
                'workspace_instance_id': namespace, 'max_source_bytes': MAX_SOURCE_BYTES,
                'formats': ['txt', 'md'], 'storage': {'kind': 'workspace_blob', 'version': 1},
                'experimental': True,
                'message': 'Private experimental SQLite saved text; no source files, PDF reading or model execution. Not public Windows acceptance.'}


class SQLiteWorkspaceServer(WorkspaceServer):
    _service_type = SQLiteWorkspaceService


def create_sqlite_server(root, *, port=0, human=False):
    """Explicit private factory; bind loopback only, never launch browser/Run."""
    return SQLiteWorkspaceServer(root, port=port, human=human)
