import io,json,tarfile
from citeaudit.http import Cache,Response
from citeaudit.fulltext import arxiv_fulltext,Coverage

def test_binary_cache_roundtrip_and_corruption(tmp_path):
 c=Cache(tmp_path);r=Response('https://example.test/source',200,bytes(range(256)))
 c.put(r);assert c.get(r.url).body==r.body
 p=c._path(r.url);p.write_text(json.dumps({'url':r.url,'status':200,'body_base64':'@@@'}))
 assert c.get(r.url) is None

def test_long_latex_is_not_complete_text():
 blob=io.BytesIO();text=('ordinary body text '*250).encode()
 with tarfile.open(fileobj=blob,mode='w:gz') as t:
  m=tarfile.TarInfo('main.tex');m.size=len(text);t.addfile(m,io.BytesIO(text))
 class Client:
  def get(self,*a,**k):return Response('test',200,blob.getvalue())
 source=arxiv_fulltext(Client(),'1234.5678')
 assert source.words>200 and source.coverage is Coverage.EXCERPT
 assert not source.coverage.can_refute

def test_action_treats_input_as_arguments_not_shell(monkeypatch,tmp_path):
 import importlib.util
 from pathlib import Path
 from types import SimpleNamespace
 spec=importlib.util.spec_from_file_location('run_action',Path(__file__).resolve().parents[1]/'scripts/run_action.py')
 module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
 monkeypatch.chdir(tmp_path);monkeypatch.setenv('CITEAUDIT_PATHS','"$(touch injected).md"')
 monkeypatch.setenv('CITEAUDIT_FAIL_ON_FINDINGS','true')
 calls=[]
 def run(args):calls.append(args);return SimpleNamespace(returncode=2)
 monkeypatch.setattr(module.subprocess,'run',run)
 assert module.main()==2
 assert '$(touch injected).md' in calls[0] and not (tmp_path/'injected').exists()
