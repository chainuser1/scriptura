"""Score all held-out learned outputs using explicit, complete text judgments."""
import sys
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(ROOT/'tool'))
from mathematical_retrieval_experiment import read,write,digest,interval
OUT=ROOT/'local-benchmarks/retrieval-v2'


def main():
    base=read(OUT/'assistant-judgments.json')
    marks=base['judgments']
    pool=read(OUT/'learned-review-pool.json')
    decisions=read(OUT/'learned-review-decisions.json')
    assert decisions['pool_sha256']==digest(OUT/'learned-review-pool.json')
    n=0
    for q in pool['queries']:
        seen=set()
        for grade,reason,indices in decisions['queries'][q['id']]:
            assert grade in (0,1,2) and reason
            for i in indices:
                assert i not in seen
                seen.add(i)
                p=q['passages'][i]
                key=str(p['verse_id'])
                assert key not in marks[q['id']]
                marks[q['id']][key]={'grade':grade,'reason':reason,'reference':p['reference'],
                                     'origin':'held_out_learned_discovery'}
                n+=1
        assert seen==set(range(len(q['passages']))),q['id']
    write(OUT/'assistant-judgments-with-learning.json',{**base,'judgments':marks,
                                                       'learning_pool_sha256':decisions['pool_sha256']})
    learned=read(OUT/'learned-rankings.json')
    assert set(learned['train']).isdisjoint(learned['test'])
    assert learned['labels_sha256']==digest(OUT/'assistant-judgments.json')
    original={q['id']:q for q in read(OUT/'rankings.json')['queries']}
    per=[]
    for row in learned['queries']:
        qid=row['id']
        assert qid in learned['test']
        methods={**row['methods'],**{name:original[qid]['methods'][name] for name in ('compass','compass_unbalanced')}}
        y=marks[qid]
        discount=1/np.log2(np.arange(5)+2)
        ideal=np.dot(sorted([2**v['grade']-1 for v in y.values()],reverse=True)[:5],discount)
        vals={}
        for name,ranking in methods.items():
            grades=np.array([y[str(v)]['grade'] for v in ranking[:5]])
            vals[name]={'related5':float(np.mean(grades>=1)),'direct5':float(np.mean(grades==2)),
                        'ndcg5':float(np.dot(2**grades-1,discount)/ideal),'ids':ranking[:5]}
        per.append({'id':qid,'methods':vals})
    summary={}
    for name in per[0]['methods']:
        delta=[q['methods'][name]['ndcg5']-q['methods']['compass']['ndcg5'] for q in per]
        summary[name]={m:float(np.mean([q['methods'][name][m] for q in per])) for m in ('related5','direct5','ndcg5')}
        summary[name].update({'ndcg_delta':float(np.mean(delta)),'ci95':interval(delta,[q['id'] for q in per])})
    write(OUT/'learned-results.json',{'provenance':'Assistant judgments; exploratory held-out intents, not independent reader accuracy',
                                     'new_judgments':n,'summary':summary,'per_query':per})
    # Extend the portable evaluation key, preserving its initial anchor review.
    export=read(ROOT/'tool/search_anchors_v2.json')
    for q in export['queries']:
        qid=q['id']
        for v in marks[qid].values():
            if v.get('origin')!='held_out_learned_discovery':
                continue
            entry={k:v[k] for k in ('reference','grade','reason')}
            field='anchors' if v['grade']>0 else 'reviewed_nonanswers'
            if v['grade']==0:
                entry.pop('grade')
            if not any(x['reference']==v['reference'] for x in q[field]):
                q[field].append(entry)
    export['learning_pool_sha256']=decisions['pool_sha256']
    write(ROOT/'tool/search_anchors_v2.json',export)
    lines=['# Exploratory learned rankers: 12 held-out challenge intents','',
           'Training uses only the 24 development intents. Assistant judgments; no production change.',
           'Full-corpus failures and the post-inspection candidate-domain diagnostic are both retained.','',
           '| Method | Related P@5 | Direct P@5 | Pooled nDCG@5 | Delta vs Compass [95%] |','|---|---:|---:|---:|---|']
    for name,v in summary.items():
        lo,hi=v['ci95']
        lines.append(f'| {name} | {v["related5"]:.3f} | {v["direct5"]:.3f} | {v["ndcg5"]:.3f} | {v["ndcg_delta"]:+.3f} [{lo:+.3f}, {hi:+.3f}] |')
    (OUT/'learned-report.md').write_text('\n'.join(lines)+'\n','utf-8')
    print('Validated',n,'new judgments;',sum(map(len,marks.values())),'total judgments')
    print('\n'.join(lines))


if __name__=='__main__':
    main()
