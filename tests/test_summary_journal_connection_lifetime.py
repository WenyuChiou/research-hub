"""Explicit mutation-fixture connection ownership, independent of garbage collection."""
import sqlite3
from unittest.mock import patch

def test_mutation_fixtures_close_connections_before_return():
    from tests.test_summary_journal import JournalTests
    from tests.test_summary_journal_apply import ApplyTests
    from tests import test_summary_journal_fault_boundaries as faults

    connections=[];real=sqlite3.connect
    class Tracked(sqlite3.Connection):
        closed=False
        def close(self):self.closed=True;return super().close()
    def connect(*args,**kwargs):
        kwargs['factory']=Tracked;c=real(*args,**kwargs);connections.append(c);return c
    try:
        with patch.object(sqlite3,'connect',connect):
            for cls,name in [(JournalTests,'test_persisted_authorization_is_revalidated_before_dispatch'),(JournalTests,'test_persisted_source_and_targets_are_revalidated'),(ApplyTests,'test_old_private_schema_is_rejected_without_migration')]:
                case=cls(name);case.setUp()
                try:getattr(case,name)()
                finally:case.doCleanups()
            gen=faults.setup.__wrapped__();fixture=next(gen)
            try:faults.test_corrupt_staged_material_blocks_actual_apply_without_destination_io(fixture)
            finally:
                try:next(gen)
                except StopIteration:pass
        leaked=sum(not c.closed for c in connections)
        print({'connections':len(connections),'unclosed':leaked},flush=True)
        assert leaked==0,'Mutation fixtures retained open SQLite connections'
    finally:
        for c in connections:
            if not c.closed:c.close()
