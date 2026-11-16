"""POSIX read boundary regression, without DB/provider setup dependencies."""
import os
from types import SimpleNamespace

import pytest

from research_hub.workspace.core import WorkspaceError
from research_hub.workspace.native_summary import read_path
from research_hub.workspace import text_intake

pytestmark = pytest.mark.skipif(os.name != 'posix', reason='Native POSIX read primitives')


@pytest.mark.parametrize('raw,limit', [(b'',0),(b'abc',3),('Synthetic \u4e2d\u6587'.encode(),100)])
def test_posix_bounded_regular_read(tmp_path, raw, limit):
    (tmp_path / 'source.txt').write_bytes(raw)
    assert read_path(SimpleNamespace(root=tmp_path), 'source.txt', limit) == raw


def test_posix_limit_plus_one_fails_closed(tmp_path):
    (tmp_path / 'source.txt').write_bytes(b'abcd')
    with pytest.raises(WorkspaceError) as error:
        read_path(SimpleNamespace(root=tmp_path), 'source.txt', 3)
    assert error.value.code == 'context_limit'


@pytest.mark.parametrize('path',['../outside','/absolute','a//b','./file','a/../file','a\\file'])
def test_posix_bad_path_rejected(tmp_path,path):
    with pytest.raises(WorkspaceError) as error:
        read_path(SimpleNamespace(root=tmp_path),path,20)
    assert error.value.code == 'unsafe_path'


@pytest.mark.parametrize('kind',['leaf','ancestor','root'])
def test_posix_links_refused(tmp_path,kind):
    selected=tmp_path/'selected'; selected.mkdir()
    other=tmp_path/'other';other.mkdir();(other/'input.txt').write_bytes(b'other synthetic scope')
    if kind=='leaf':
        (selected/'input.txt').symlink_to(other/'input.txt');root=selected;path='input.txt'
    elif kind=='ancestor':
        (selected/'link').symlink_to(other,target_is_directory=True);root=selected;path='link/input.txt'
    else:
        root=tmp_path/'root-link';root.symlink_to(selected,target_is_directory=True);path='input.txt'
    with pytest.raises(WorkspaceError):read_path(SimpleNamespace(root=root),path,100)
    assert (other/'input.txt').read_bytes()==b'other synthetic scope'


def test_posix_changed_parent_rejected_before_return(tmp_path,monkeypatch):
    selected=tmp_path/'selected';selected.mkdir();(selected/'input.txt').write_bytes(b'original synthetic')
    moved=tmp_path/'moved';original=text_intake._read_file
    def changed(directory,name,**kwargs):
        selected.rename(moved);selected.mkdir();(selected/'input.txt').write_bytes(b'replacement synthetic')
        return original(directory,name,**kwargs)
    monkeypatch.setattr(text_intake,'_read_file',changed)
    with pytest.raises(WorkspaceError) as error:
        read_path(SimpleNamespace(root=tmp_path),'selected/input.txt',100)
    assert error.value.code=='unsafe_path'
    assert (moved/'input.txt').read_bytes()==b'original synthetic'


def test_posix_missing_redacted(tmp_path):
    with pytest.raises(WorkspaceError) as error:
        read_path(SimpleNamespace(root=tmp_path),'private-name.txt',100)
    assert error.value.code=='source_unavailable'
    assert 'private-name' not in str(error.value)
