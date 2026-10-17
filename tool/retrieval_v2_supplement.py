"""Resolve supplemental anchor candidates; never infer their grades."""
import json
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(ROOT/'tool'))
from mathematical_retrieval_experiment import Store, read, write

if __name__=='__main__':
    out=ROOT/'local-benchmarks/retrieval-v2'
    store=Store()
    ids={store.ref(v):int(v) for v in store.ids}
    pool=read(out/'review-pool.json')['queries']
    existing={q['id']:{p['verse_id'] for p in q['passages']} for q in pool}
    candidates={}
    for q,refs in read(ROOT/'tool/retrieval_v2_supplement.json')['references'].items():
        candidates[q]=[]
        print('\n'+q)
        for ref in refs:
            assert ref in ids,ref
            v=ids[ref]
            if v in existing[q]:
                continue
            entry={'verse_id':v,'reference':ref,'text':store.text(v)}
            candidates[q].append(entry)
            print(f'{len(candidates[q])-1} | {ref} | {entry["text"]}')
    write(out/'supplement-pool.json',{'provenance':'Assistant-nominated additional candidates; no ranks/scores used','queries':candidates})
