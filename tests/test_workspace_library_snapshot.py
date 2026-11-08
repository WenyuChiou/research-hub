import http.client
import json
import os
from pathlib import Path
import threading

import pytest

from research_hub.workspace import library_snapshot as module
from research_hub.workspace.server import WorkspaceServer


def payload():
    return {"schema_version":1,"captured_at":"2026-11-01T00:00:00Z","vault_label":"Synthetic vault",
            "read_only":True,"body_read":False,"collections":[{"id":"selected","name":"Selected","note_count":1}],
            "notes":[{"id":"obsidian:"+"a"*24,"kind":"library-note","data":{"title":"Synthetic saved note",
                "origin":"obsidian","read_only":True,"note_path":"raw/selected/note.md","reading_level":"note-metadata",
                "abstract":"Saved synthetic abstract","identity_status":"unverified","metadata_status":"available"}}]}


def test_selected_snapshot_is_projected_without_config_body_or_unknown_fields(tmp_path, monkeypatch):
    path=tmp_path/"selected.json"; value=payload()
    value["secret"]="NOT_ALLOWED"; value["notes"][0]["data"]["body"]="NOT_ALLOWED"
    path.write_text(json.dumps(value),encoding="utf-8"); before=path.read_bytes()
    from research_hub import config
    monkeypatch.setattr(config,"get_config",lambda *a,**k:pytest.fail("No config discovery"))
    result=module.LibrarySnapshot(path).read()
    assert result["notes"][0]["data"]["abstract"]=="Saved synthetic abstract"
    assert result["body_read"] is False and "NOT_ALLOWED" not in json.dumps(result)
    assert path.read_bytes()==before


def test_unconfigured_reader_does_not_probe_any_path(monkeypatch):
    monkeypatch.setattr(module,"_metadata",lambda *a:pytest.fail("No file scope"))
    assert module.LibrarySnapshot().read()["status"]=="unknown"


@pytest.mark.parametrize("change", ["timestamp","scope","kind","id","escape","terms","size","schema","reading-depth","identity","record-type"])
def test_invalid_snapshots_remain_unknown_without_raw_error_disclosure(tmp_path,change):
    value=payload(); data=value["notes"][0]["data"]
    if change=="timestamp":value["captured_at"]="PRIVATE_INVALID_TIMESTAMP"
    if change=="scope":value["body_read"]=True
    if change=="kind":value["notes"][0]["kind"]="source"
    if change=="id":value["notes"][0]["id"]="private-source"
    if change=="escape":data["note_path"]="../PRIVATE/secret.md"
    if change=="terms":data["tags"]=[{}]
    if change=="size":data["note_size_bytes"]=True
    if change=="schema":value["schema_version"]=True
    if change=="reading-depth":data["reading_level"]="full-text"
    if change=="identity":data["identity_status"]="human-reviewed"
    if change=="record-type":data["record_type"]="full-text"
    path=tmp_path/"PRIVATE.json"; path.write_text(json.dumps(value),encoding="utf-8")
    result=module.LibrarySnapshot(path).read()
    assert result["status"]=="unknown" and result["code"]=="library_snapshot_unavailable"
    assert "PRIVATE" not in json.dumps(result) and str(tmp_path) not in json.dumps(result)


@pytest.mark.parametrize("depth",["root","note"])
def test_duplicate_snapshot_json_keys_are_unknown(tmp_path,depth):
    raw=json.dumps(payload())
    raw=raw.replace('"schema_version": 1','"schema_version": 99, "schema_version": 1') if depth=="root" else raw.replace('"origin": "obsidian"','"origin": "private", "origin": "obsidian"')
    path=tmp_path/"selected.json";path.write_text(raw,encoding="utf-8")
    assert module.LibrarySnapshot(path).read()["status"]=="unknown"


def test_missing_and_oversized_snapshot_are_unknown(tmp_path,monkeypatch):
    path=tmp_path/"missing.json"
    assert module.LibrarySnapshot(path).read()["status"]=="unknown"
    path.write_text(json.dumps(payload()),encoding="utf-8")
    monkeypatch.setattr(module,"MAX_SNAPSHOT_BYTES",4)
    assert module.LibrarySnapshot(path).read()["status"]=="unknown"


def test_linked_snapshot_is_rejected_before_open(tmp_path,monkeypatch):
    path=tmp_path/"selected.json"; path.write_text(json.dumps(payload()),encoding="utf-8")
    original=path.read_bytes(); alias=tmp_path/"alias.json"; os.link(path,alias)
    original_open=module.os.open
    def guarded_open(candidate,*args,**kwargs):
        if candidate==alias or candidate==str(alias):
            pytest.fail("No linked read")
        return original_open(candidate,*args,**kwargs)
    monkeypatch.setattr(module.os,"open",guarded_open)
    # The observer must not break unrelated descriptor-based fixture cleanup.
    control=tmp_path/"ordinary-control.txt";control.write_text("Synthetic",encoding="utf-8")
    descriptor=os.open(control,os.O_RDONLY);os.close(descriptor)
    assert module.LibrarySnapshot(alias).read()["status"]=="unknown"
    assert path.read_bytes()==original


def test_changed_snapshot_identity_is_unknown_before_read(tmp_path,monkeypatch):
    path=tmp_path/"selected.json"; path.write_text(json.dumps(payload()),encoding="utf-8")
    original=module.os.fstat
    def changed(fd):
        info=original(fd); values=list(info); values[6]+=1
        return os.stat_result(values)
    monkeypatch.setattr(module.os,"fstat",changed)
    monkeypatch.setattr(module.os,"read",lambda *a:pytest.fail("Changed file must not read"))
    assert module.LibrarySnapshot(path).read()["status"]=="unknown"


def get(server,path,headers=None):
    connection=http.client.HTTPConnection("127.0.0.1",server.server_port,timeout=4)
    try:
        connection.request("GET",path,headers=headers or {})
        response=connection.getresponse()
        return response.status,json.loads(response.read())
    finally:connection.close()


def test_unconfigured_http_endpoint_is_explicitly_unknown(tmp_path):
    server=WorkspaceServer(tmp_path,port=0); thread=threading.Thread(target=server.serve_forever);thread.start()
    try:
        status,result=get(server,"/api/v1/library/snapshot")
        assert status==404 and result["code"]=="library_snapshot_unavailable" and result["status"]=="unknown"
    finally:
        server.shutdown();server.server_close();thread.join(timeout=3)
        assert not thread.is_alive()


def test_http_route_uses_only_exact_startup_file_and_keeps_origin_guard(tmp_path,monkeypatch):
    path=tmp_path/"selected.json"; path.write_text(json.dumps(payload()),encoding="utf-8")
    server=WorkspaceServer(tmp_path/"workspace",port=0,library_snapshot=path)
    thread=threading.Thread(target=server.serve_forever);thread.start()
    try:
        status,result=get(server,"/api/v1/library/snapshot")
        assert status==200 and result==payload()
        monkeypatch.setattr(server.library_snapshot,"read",lambda:pytest.fail("Reject before read"))
        assert get(server,"/api/v1/library/snapshot?path=other.json")[0]==400
        assert get(server,"/api/v1/library/snapshot",{"Origin":"https://outside.invalid"})[0]==403
        assert get(server,"/api/v1/library/snapshot",{"Sec-Fetch-Site":"cross-site"})[0]==403
    finally:
        server.shutdown();server.server_close();thread.join(timeout=3)
        assert not thread.is_alive()


def test_cli_snapshot_is_explicit_and_workspace_only(tmp_path,monkeypatch):
    from research_hub import cli
    from research_hub.workspace import server
    monkeypatch.setattr(cli,"get_config",lambda *a,**k:pytest.fail("No config discovery"))
    monkeypatch.setattr(cli,"require_config",lambda *a,**k:pytest.fail("No config discovery"))
    calls=[];monkeypatch.setattr(server,"serve_workspace",lambda *a,**k:calls.append((a,k)))
    with pytest.raises(SystemExit):cli.main(["serve","--library-snapshot",str(tmp_path/"selected.json")])
    assert not calls
    assert cli.main(["serve","--workspace","--root",str(tmp_path/"workspace"),"--library-snapshot",str(tmp_path/"selected.json"),"--no-browser"])==0
    assert calls[0][1]["library_snapshot"]==str(tmp_path/"selected.json")
