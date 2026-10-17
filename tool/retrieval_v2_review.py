"""Display rank-blinded corpus text and validate explicit review decisions."""
import argparse
import hashlib
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parent.parent
OUT=ROOT/'local-benchmarks/retrieval-v2'


def load(name):
    return json.loads((OUT/name).read_text('utf-8'))


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--start',type=int,default=0)
    ap.add_argument('--count',type=int,default=3)
    ap.add_argument('--compile',action='store_true')
    args=ap.parse_args()
    pool=load('review-pool.json')
    if not args.compile:
        for q in pool['queries'][args.start:args.start+args.count]:
            print('\nQUERY',q['id'],q['query'])
            for i,p in enumerate(q['passages']):
                print(f'{i} | {p["reference"]} | {p["text"]}')
        return
    decisions=load('review-decisions.json')
    digest=hashlib.sha256((OUT/'review-pool.json').read_bytes()).hexdigest()
    assert decisions['pool_sha256']==digest, 'Review refers to a different pool'
    out={}
    for q in pool['queries']:
        assert q['id'] in decisions['queries'],q['id']
        marks={}
        for grade,reason,indices in decisions['queries'][q['id']]:
            assert grade in (0,1,2) and reason.strip()
            for i in indices:
                p=q['passages'][i]
                key=str(p['verse_id'])
                assert key not in marks,(q['id'],i)
                marks[key]={'grade':grade,'reason':reason,'reference':p['reference'],
                            'text_sha256':hashlib.sha256(p['text'].encode()).hexdigest()}
        assert len(marks)==len(q['passages']),(q['id'],'missing',
                    [i for i,p in enumerate(q['passages']) if str(p['verse_id']) not in marks])
        out[q['id']]=marks
    if 'supplement_queries' in decisions:
        supplement=load('supplement-pool.json')
        extra_digest=hashlib.sha256((OUT/'supplement-pool.json').read_bytes()).hexdigest()
        assert extra_digest==decisions['supplement_sha256']
        for q,passages in supplement['queries'].items():
            seen=set()
            for grade,reason,indices in decisions['supplement_queries'][q]:
                assert grade in (0,1,2) and reason.strip()
                for i in indices:
                    assert i not in seen
                    seen.add(i)
                    p=passages[i]
                    key=str(p['verse_id'])
                    assert key not in out[q]
                    out[q][key]={'grade':grade,'reason':reason,'reference':p['reference'],
                                 'origin':'supplement', 'text_sha256':hashlib.sha256(p['text'].encode()).hexdigest()}
            assert seen==set(range(len(passages))),q
    result={'provenance':'assistant_text_review','reviewer':'Codex assistant',
            'pool_sha256':digest,'independent_human_review':False,
            'rubric':{'0':'Does not address the expressed need','1':'Meaningfully related but incomplete or context-dependent',
                      '2':'Directly addresses or supports the expressed need'},'judgments':out}
    (OUT/'assistant-judgments.json').write_text(json.dumps(result,indent=2,ensure_ascii=False),'utf-8')
    print('Validated',len(out),'queries and',sum(map(len,out.values())),'explicit text judgments')


if __name__=='__main__':
    main()
