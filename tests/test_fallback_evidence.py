"""Adverse authority states must not become completed negative evidence."""
from types import SimpleNamespace
import pytest
from citeaudit.http import NotFound, Unreachable
from citeaudit.models import Citation, Finding, Kind, Report, Verdict
from citeaudit.verify import Verifier


def raise_miss(*args, **kwargs):
    raise NotFound('fixture: no record')


def raise_outage(*args, **kwargs):
    raise Unreachable('fixture: service unavailable')


@pytest.mark.parametrize('kind',[Kind.DOI,Kind.BIBLIOGRAPHIC])
@pytest.mark.parametrize('mode',['outage','disabled','miss'])
def test_secondary_states_stay_distinct(kind,mode):
    v=Verifier(client=object(),workers=1,use_fallback=mode!='disabled')
    v.crossref=SimpleNamespace(resolve=raise_miss,search=lambda *a,**k:[])
    calls=[]
    def secondary(*args,**kwargs):
        calls.append(1)
        if mode=='disabled':raise AssertionError('disabled fallback must not run')
        if mode=='outage':raise_outage()
        raise_miss()
    v.openalex=SimpleNamespace(resolve_doi=secondary,search_title=secondary)
    c=Citation(raw='fixture',kind=kind,identifier='10.1234/fixture',claimed_title='A specific title for the offline fixture')
    finding=v.check(c)
    expected={'outage':Verdict.UNREACHABLE,'disabled':Verdict.UNVERIFIABLE,'miss':Verdict.NOT_FOUND}[mode]
    assert finding.verdict is expected
    report=Report(document='synthetic',findings=[finding])
    assert report.conclusive==(1 if mode=='miss' else 0)
    assert len(report.failures)==(1 if mode=='miss' else 0)
    assert len(calls)==(0 if mode=='disabled' else 1)
    if mode=='disabled':assert finding.authority=='crossref'
    if mode=='outage':assert 'No negative OpenAlex result' in finding.detail


def test_partial_coverage_does_not_imply_full_document_success():
    citation=Citation(raw='fixture',kind=Kind.DOI)
    report=Report(document='synthetic',findings=[Finding(citation=citation,verdict=v,authority='fixture',detail='synthetic')
                  for v in [Verdict.VERIFIED,Verdict.UNREACHABLE,Verdict.UNVERIFIABLE]])
    s=report.summary()
    assert s['integrity_score']==1
    assert s['check_coverage']==pytest.approx(1/3)
    assert s['all_citation_pass_share_bounds']==[1/3,1]
    assert report.failures==[]


def test_empty_and_all_inconclusive_denominators():
    assert Report(document='empty').summary()['all_citation_pass_share_bounds'] is None
    c=Citation(raw='fixture',kind=Kind.DOI)
    r=Report(document='synthetic',findings=[Finding(citation=c,verdict=Verdict.UNREACHABLE,authority='fixture',detail='outage')])
    assert r.summary()['all_citation_pass_share_bounds']==[0,1]
    assert r.summary()['integrity_score'] is None
