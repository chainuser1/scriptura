"""Recheck pack hashes and every v2 baseline against the native engine."""
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(ROOT/'tool'))
import mathematical_retrieval_experiment as experiment

if __name__=='__main__':
    experiment.OUT=ROOT/'local-benchmarks/retrieval-v2'
    pack=ROOT/'generated-artifacts/engine-pack'
    checks={p:experiment.digest(pack/p)==meta['sha256']
            for p,meta in experiment.read(pack/'manifest.json')['files'].items()}
    assert all(checks.values()),checks
    experiment.write(experiment.OUT/'artifact-verification.json',checks)
    queries=[]
    for q in experiment.read(experiment.OUT/'rankings.json')['queries']:
        row={'query':q['query'],'methods':{n:{'ids':q['methods'][n][:10]} for n in ('compass','lantern')}}
        # Existing parity helper samples every 24th item; repeat only the wrapper.
        queries.extend([row]*24)
    result=experiment.native_parity(None,{'queries':queries})
    print('Verified',len(checks),'pack files and',len(result),'native rankings')
