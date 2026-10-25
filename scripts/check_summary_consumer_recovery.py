"""Source-bound consumer projection audit; not full CLI/MCP runtime acceptance.
Only frozen functions/classes extracted unchanged, external model/storage seams fake.
"""
import ast,contextlib,dataclasses,io,json,socket,subprocess,sys,types
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]/'src/research_hub'
def forbidden(*a,**k):raise AssertionError('Network/subprocess forbidden')
socket.create_connection=forbidden;subprocess.Popen=forbidden
class NoSocket(socket.socket):
 def __init__(self,*a,**k):forbidden()
socket.socket=NoSocket
ns={'__name__':'consumer_probe','dataclass':dataclasses.dataclass,'field':dataclasses.field,'Path':Path,'sys':sys,'json':json,'is_dataclass':dataclasses.is_dataclass,'asdict':dataclasses.asdict}
sys.modules['consumer_probe']=types.ModuleType('consumer_probe');sys.modules['consumer_probe'].__dict__.update(ns)
ns=sys.modules['consumer_probe'].__dict__
def extract(file,names):
 tree=ast.parse((ROOT/file).read_text());selected=[]
 for node in tree.body:
  if isinstance(node,(ast.FunctionDef,ast.ClassDef)) and node.name in names:
   if isinstance(node,ast.FunctionDef):node.decorator_list=[]
   selected.append(node)
 assert len(selected)==len(names),(file,names)
 mod=ast.Module(body=[ast.ImportFrom(module='__future__',names=[ast.alias(name='annotations')],level=0),*selected],type_ignores=[])
 exec(compile(ast.fix_missing_locations(mod),str(ROOT/file),'exec'),ns)
extract('summarize.py',['SummaryApplyResult','SummaryReport','summarize_cluster'])
Result,Report=ns['SummaryApplyResult'],ns['SummaryReport']
errors=['first: known pre-write rejection','second: zotero write outcome unknown; local rollback unavailable; inspect both destinations before retrying']
result=Result('synthetic',applied=['good'],skipped=['duplicate not retried'],errors=errors,obsidian_writes=1,zotero_writes=1,warnings=['human note preserved'])
# Execute actual report projection using fake external generation/application seams.
ns.update(build_summarize_prompt=lambda *a,**k:'synthetic',detect_llm_cli=lambda:'fake',_invoke_llm_cli=lambda *a:'{}',_extract_first_json=lambda x:{},apply_summaries=lambda *a,**k:result)
llm=types.ModuleType('research_hub.llm_cli');llm._extract_first_json=lambda x:{};llm.detect_llm_cli=lambda:'fake';llm.invoke_llm_cli=lambda *a:'{}'
sys.modules['research_hub']=types.ModuleType('research_hub');sys.modules['research_hub'].__path__=[];sys.modules['research_hub.llm_cli']=llm
report=ns['summarize_cluster'](object(),'synthetic',apply=True,llm_cli='fake')
assert report.ok is False and report.apply_result is result and errors[1] not in report.error
pkg=types.ModuleType('research_hub');pkg.__version__='synthetic';pkg.__path__=[]
summary=types.ModuleType('research_hub.summarize');summary.summarize_cluster=lambda *a,**k:report;summary.apply_summaries=lambda *a,**k:result
paper=types.ModuleType('research_hub.paper_summarize');layer2=[];paper.summarize_pending=lambda *a,**k:layer2.append(k) or []
config=types.ModuleType('research_hub.config');config.get_config=lambda:object()
pkg.summarize=summary
sys.modules.update({'research_hub':pkg,'research_hub.summarize':summary,'research_hub.paper_summarize':paper,'research_hub.config':config})
extract('cli_common.py',['_json_safe','_emit_cli_json']);extract('cli_summarize.py',['_cmd_summarize'])
args=types.SimpleNamespace(cluster='synthetic',llm_cli='fake',apply=True,no_zotero=False,no_obsidian=False)
checks=[]
out,err=io.StringIO(),io.StringIO()
with contextlib.redirect_stdout(out),contextlib.redirect_stderr(err):rc=ns['_cmd_summarize'](args,object())
checks.append(dict(case='text-cli-complete-receipt',desired_pass=errors[1] in err.getvalue() and 'applied: 1' in out.getvalue(),rc=rc,stdout=out.getvalue(),stderr=err.getvalue()))
out=io.StringIO()
with contextlib.redirect_stdout(out):rc=ns['_cmd_summarize'](args,object(),emit_json=True)
receipt=json.loads(out.getvalue());assert receipt['report']['apply_result']['errors']==errors
checks.append(dict(case='json-cli-full-error-countercase',desired_pass=True))
extract('auto.py',['_run_summary_step']);steps=[]
ns.update(_step_log=lambda report,name,ok,elapsed,detail,progress:steps.append(dict(name=name,ok=ok,detail=detail)),_elapsed=lambda *a:0)
ns['_run_summary_step'](object(),'synthetic','fake',object(),0,False)
checks.append(dict(case='auto-no-secondary-write-after-unknown',desired_pass=len(layer2)==0,secondary_calls=len(layer2),steps=list(steps)))
checks.append(dict(case='auto-full-details-partial-success-count',desired_pass=any(errors[1] in step['detail'] for step in steps) and any('1 ok' in step['detail'] for step in steps)))
extract('zotero/enrich.py',['apply_enrichment'])
ns.update(time=types.SimpleNamespace(sleep=lambda _:None),_index_cluster_notes=lambda *a:{'PARENT':'fake-note'},_rewrite_note_abstract=lambda *a,**k:True,_note_summary_has_todo=lambda *a:True)
zot=types.SimpleNamespace(item=lambda key:{'data':{'abstractNote':''}},update_item=lambda data:True)
plan=types.SimpleNamespace(item_key='PARENT',fields_to_fill={'abstractNote':'synthetic'},abstract_source='synthetic')
out=io.StringIO()
with contextlib.redirect_stdout(out):enriched=ns['apply_enrichment'](zot,[plan],cfg=object(),cluster_slug='synthetic')
checks.append(dict(case='enrich-full-error-guidance',desired_pass=errors[1] in out.getvalue(),stdout=out.getvalue(),enrichment_result=enriched))
extract('mcp_server.py',['apply_cluster_summaries']);ns.update(_validate_mcp_args=lambda **k:k,_tool_error=lambda e:{'error':str(e)})
mcp=ns['apply_cluster_summaries']('synthetic',{})
assert mcp['errors']==errors and mcp['applied']==['good'];checks.append(dict(case='mcp-apply-full-receipt-countercase',desired_pass=True))
# Success remains eligible for second layer; no assertion asks for blanket shutdown.
report=Report('synthetic',apply_result=Result('synthetic',applied=['good']))
layer2.clear();steps.clear();ns['_run_summary_step'](object(),'synthetic','fake',object(),0,False)
assert len(layer2)==1;checks.append(dict(case='auto-success-secondary-layer-countercase',desired_pass=True))
print(json.dumps(checks,indent=2))
assert all(c['desired_pass'] for c in checks),'Expected red consumer boundaries'
# Resummarize text route also must retain every error and partial success.
import tempfile
report=Report('synthetic',ok=False,error='Two entries require attention: '+errors[0],apply_result=result)
with tempfile.TemporaryDirectory(prefix='hub-consumer-notes-') as td:
 raw=Path(td);(raw/'synthetic').mkdir();(raw/'synthetic/paper.md').write_text('Synthetic placeholder only')
 cfg=types.SimpleNamespace(raw=raw,clusters_file=raw/'unused.json')
 ns.update(get_config=lambda:cfg,ClusterRegistry=lambda _:types.SimpleNamespace(get=lambda _:types.SimpleNamespace(obsidian_subfolder='synthetic',slug='synthetic')),_summary_block_has_todo=lambda _:True,_read_zotero_key_from_frontmatter=lambda _:'SYNTHETIC')
 extract('cli_paper.py',['_paper_resummarize']);out,err=io.StringIO(),io.StringIO()
 with contextlib.redirect_stdout(out),contextlib.redirect_stderr(err):rc=ns['_paper_resummarize']('synthetic',apply=True,llm_cli='fake')
 assert rc==1 and errors[1] in err.getvalue() and 'applied: 1' in out.getvalue()
 print(json.dumps({'case':'resummarize-complete-receipt','status':'PASS'}))
# An exception with no receipt cannot be treated as permission for another writer.
summary.summarize_cluster=lambda *a,**k:(_ for _ in ()).throw(RuntimeError('Synthetic interrupted layer1'))
layer2.clear();steps.clear();ns['_run_summary_step'](object(),'synthetic','fake',object(),0,False)
assert not layer2 and any('deferred' in step['detail'] for step in steps)
print(json.dumps({'case':'layer1-exception-defers-secondary-write','status':'PASS'}))
