"""Offline retrieval research and method-blinded pooled evidence. No app imports.

Run .venv/Scripts/python.exe -I tool/retrieval_v2.py
Then supply explicit assistant judgments with --score (never inferred from ranks).
"""
import argparse
import hashlib
import json
import sys
import time
from pathlib import Path

import numpy as np
from scipy.special import erf, logsumexp
from threadpoolctl import threadpool_limits

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'tool'))
from mathematical_retrieval_experiment import Store, TokenPack, norm, order, z, read, write, digest, interval
from volume_balance import balance

OUT = ROOT / 'local-benchmarks/retrieval-v2'
SEED = 20261016


def query_set():
    old = read(ROOT / 'tool/query_robustness_set.json')['intents']
    return ([{'id': x['id'], 'query': x['variants']['formal'], 'split': 'development',
              'anchors_from': x['anchors_from']} for x in old]
            + [{**x, 'split': 'challenge'} for x in read(ROOT / 'tool/retrieval_challenge_set.json')['queries']])


def encode_queries(store, queries):
    import onnxruntime as ort
    from tokenizers import Tokenizer
    pack = ROOT / 'generated-artifacts/engine-pack'
    manifest = read(pack / 'manifest.json')
    identity = {'queries': queries, 'engine': digest(pack / 'manifest.json'), 'schema': 1}
    cache = OUT / 'encoded.npz'
    if cache.exists():
        assert read(OUT / 'encoded-identity.json') == identity, 'Stale encoded cache'
        return dict(np.load(cache))
    so = ort.SessionOptions()
    so.intra_op_num_threads = 4
    so.inter_op_num_threads = 1
    sess = ort.InferenceSession(str(pack / manifest['encoder_file']), so, providers=['CPUExecutionProvider'])
    tok = Tokenizer.from_file(str(pack / 'tokenizer.json'))
    head = {k: v.astype(np.float32) for k, v in np.load(pack / 'head.npz').items()}
    fw = manifest['identity']['fusion']['family_weights']
    genes = (pack / 'retrieval/gene_ids.txt').read_text().splitlines()
    sw = np.sqrt(np.array([fw.get(g[0], fw['default']) for g in genes], dtype=np.float32))
    data = {}
    for i, q in enumerate(queries):
        tokens = np.array([tok.encode(q['query']).ids], dtype=np.int64)
        assert 2 < tokens.shape[1] <= 512
        dense, weights, col = sess.run(None, {'input_ids': tokens, 'attention_mask': np.ones_like(tokens)})
        d = dense[0]
        h = d @ head['w0'].T + head['b0']
        h = .5 * h * (1 + erf(h / np.sqrt(2)))
        g = 1 / (1 + np.exp(-(h @ head['w1'].T + head['b1'])))
        sparse_query = np.zeros(store.S.shape[1], np.float32)
        for tid, w in zip(tokens[0], weights.reshape(-1)):
            if tid > 3:
                sparse_query[tid] = max(sparse_query[tid], w)
        data[f'd{i}'], data[f'g{i}'], data[f'gw{i}'], data[f'c{i}'] = d, norm(g), norm(g*sw), col[0]
        data[f's{i}'] = np.asarray(store.S @ sparse_query, dtype=np.float64)
        print(f'encoded {i+1}/{len(queries)}', flush=True)
    np.savez_compressed(cache, **data)
    write(OUT / 'encoded-identity.json', identity)
    return data


def full_colbert(pack, encoded, queries):
    path = OUT / 'exact-colbert.npy'
    if path.exists():
        a = np.load(path)
        assert a.shape == (len(queries), sum(len(c)-1 for c in pack.cum))
        return a
    qs = [encoded[f'c{i}'] for i in range(len(queries))]
    qcat = np.concatenate(qs)
    offsets = np.r_[0, np.cumsum([len(q) for q in qs])]
    all_scores = []
    started = time.perf_counter()
    for shard, (vectors, cum) in enumerate(zip(pack.vec, pack.cum)):
        # Limit temporary matrix to roughly 64 MB; one full scan per query.
        doc_scores = []
        for start in range(0, len(cum)-1, 128):
            stop = min(start+128, len(cum)-1)
            sim = qcat @ vectors[cum[start]:cum[stop]].astype(np.float32).T
            token_max = np.maximum.reduceat(sim, cum[start:stop]-cum[start], axis=1)
            doc_scores.append(np.stack([token_max[offsets[i]:offsets[i+1]].mean(0) for i in range(len(qs))]))
        all_scores.append(np.concatenate(doc_scores, axis=1))
        print(f'exact ColBERT shard {shard+1}/{len(pack.vec)} ({time.perf_counter()-started:.0f}s)', flush=True)
    result = np.concatenate(all_scores, axis=1)
    # Separate existing implementation, sampled corpus rows, all query lengths.
    rows = np.random.default_rng(SEED).choice(result.shape[1], 61, replace=False)
    errors = [float(np.max(np.abs(pack.maxsim(q, rows)-result[i, rows]))) for i,q in enumerate(qs)]
    assert max(errors) < 2e-5, errors
    np.save(path, result)
    write(OUT / 'colbert-verification.json', {'sampled_rows': rows.tolist(), 'max_absolute_errors': errors,
                                           'seconds': time.perf_counter()-started})
    return result


def geometry(store):
    cache = OUT / 'geometry.npz'
    if cache.exists():
        return dict(np.load(cache))
    x = store.D
    mean = x.mean(0)
    centered = x-mean
    cov = (centered.T @ centered)/(len(x)-1)
    eigen, vec = np.linalg.eigh(cov.astype(np.float64))
    shrinkage = .1*eigen.mean()
    transform = ((vec * np.maximum(eigen+shrinkage, 1e-12)**(-.25)) @ vec.T).astype(np.float32)
    white = norm(centered @ transform)
    reference = np.random.default_rng(SEED).choice(len(x), 8192, replace=False)
    density = np.empty(len(x), np.float32)
    lookup = {int(row): j for j,row in enumerate(reference)}
    for start in range(0, len(x), 256):
        stop = min(start+256, len(x))
        sims = x[start:stop] @ x[reference].T
        for row in range(start, stop):
            if row in lookup:
                sims[row-start, lookup[row]] = -np.inf
        density[start:stop] = np.partition(sims, -10, axis=1)[:, -10:].mean(1)
    out = {'mean': mean, 'transform': transform, 'white': white, 'centered': norm(centered), 'density': density}
    np.savez_compressed(cache, **out)
    return out


def transport(q, d, unbalanced=False):
    cost = 1 - q.astype(np.float64) @ d.astype(np.float64).T
    n,m = cost.shape
    la, lb = np.full(n, -np.log(n)), np.full(m, -np.log(m))
    eps, tau = .05, .5
    logk = la[:,None] + lb[None,:] - cost/eps
    power = tau/(tau+eps) if unbalanced else 1.
    u, v = np.zeros(n), np.zeros(m)
    converged = False
    for step in range(1000):
        oldv = v.copy()
        u = power*(la-logsumexp(logk+v[None,:], axis=1))
        v = power*(lb-logsumexp(logk+u[:,None], axis=0))
        if np.max(np.abs(v-oldv)) < 1e-7:
            converged = True
            break
    logp = logk+u[:,None]+v[None,:]
    p = np.exp(logp)
    a, b = p.sum(1), p.sum(0)
    kl = np.sum(p*(logp-la[:,None]-lb[None,:])-p)+1
    objective = np.sum(p*cost)+eps*kl
    if unbalanced:
        objective += tau*(np.sum(a*(np.log(a.clip(1e-300))-la)-a)+1
                          +np.sum(b*(np.log(b.clip(1e-300))-lb)-b)+1)
    marginal_error = max(np.max(np.abs(a-1/n)), np.max(np.abs(b-1/m)))
    assert np.isfinite(objective) and converged, (step, marginal_error)
    if not unbalanced:
        assert marginal_error < 1e-6, marginal_error
    return -float(objective), {'iterations': step+1, 'mass': float(p.sum()), 'marginal_error': float(marginal_error)}


def run():
    OUT.mkdir(parents=True, exist_ok=True)
    queries = query_set()
    inputs = [ROOT/'tool/retrieval_challenge_set.json', ROOT/'tool/query_robustness_set.json',
              ROOT/'generated-artifacts/engine-pack/manifest.json', ROOT/'generated-artifacts/colbert-pack-v1/manifest.json']
    identity = {str(p.relative_to(ROOT)): digest(p) for p in inputs}
    identity['implementation'] = digest(Path(__file__))
    if (OUT/'input-identity.json').exists():
        assert read(OUT/'input-identity.json') == identity, 'Inputs/code changed; use new output directory'
    write(OUT/'input-identity.json', identity)
    store, pack = Store(), TokenPack()
    encoded = encode_queries(store, queries)
    exact = full_colbert(pack, encoded, queries)
    geo = geometry(store)
    scenarios = {s['id']: s for s in read(ROOT/'tool/seeker_scenarios.json')['scenarios']}
    refs = {store.ref(v): int(v) for v in store.ids}
    rows = np.arange(len(store.ids))
    ok = np.ones(len(rows), bool)
    results, review, checks, transport_checks = [], [], [], []
    for i,query in enumerate(queries):
        d, g, gw = encoded[f'd{i}'], encoded[f'g{i}'], encoded[f'gw{i}']
        da, ga, ra = store.Dstored @ d, store.G @ gw, store.R @ g
        sa, co = encoded[f's{i}'], exact[i]
        db, gb = balance(da, store.vol, ok, .75), balance(ga, store.vol, ok, .75)
        top = lambda x,k=200: order(x,store.ids,k)
        cb = np.unique(np.r_[top(db),top(gb),top(sa)])
        cu = np.unique(np.r_[top(da),top(ga),top(sa)])
        cr = np.unique(np.r_[top(da),top(ra),top(sa)])
        extended = np.unique(np.r_[cb,top(co)])
        raw_extended = np.unique(np.r_[cr,top(co)])
        # Freeze initial score normalization for all candidate expansion variants.
        def calibrated(x):
            return (x-x[cb].mean())/max(x[cb].std(ddof=1),1e-12)
        base = .1*calibrated(db)+.1*calibrated(sa)+.2*calibrated(co)+.6*calibrated(gb)
        ranks = {}
        def save(name, scores, cand=rows):
            ranks[name] = store.ids[cand[order(scores[cand] if len(scores)==len(rows) else scores,store.ids[cand],20)]].tolist()
        save('compass',base,cb)
        save('lantern',.25*z(db[cb])+.15*z(sa[cb])+.6*z(gb[cb]),cb)
        save('compass_unbalanced',.1*z(da[cu])+.1*z(sa[cu])+.2*z(co[cu])+.6*z(ga[cu]),cu)
        for name,scores in [('dense',da),('sparse',sa),('raw_genome',ra),('colbert_exact',co)]:
            save(name,scores)
        save('colbert_candidates',base,extended)
        raw_equal = np.mean([z(x[raw_extended]) for x in (da,sa,co,ra)],axis=0)
        save('raw_equal_colbert_candidates',raw_equal,raw_extended)
        save('dense_centered',geo['centered'] @ norm(norm(d)-geo['mean']))
        save('dense_partial_whitening',geo['white'] @ norm((norm(d)-geo['mean']) @ geo['transform']))
        save('dense_local_scaling',2*(store.D @ norm(d))-geo['density'])
        # Graph expansion from fixed initial seeds; score every neighbor on original query.
        seeds = cb[order(base[cb],store.ids[cb],8)]
        discovered = []
        existing = set(cb.tolist())
        for seed in seeds:
            for matrix in (store.D,store.R):
                sim = matrix @ matrix[seed]
                sim[seed] = -np.inf
                for row in top(sim,16):
                    if int(row) not in existing:
                        discovered.append(int(row)); existing.add(int(row))
        discovered = discovered[:256]
        save('graph_expansion',base,np.unique(np.r_[cb,discovered]).astype(int))
        deeper = np.unique(np.r_[top(db,400),top(gb,400),top(sa,400)])
        deeper = deeper[~np.isin(deeper,cb)]
        stage = .1*calibrated(db)+.1*calibrated(sa)+.6*calibrated(gb)
        extra = deeper[order(stage[deeper],store.ids[deeper],len(discovered))]
        save('deeper_candidate_control',base,np.unique(np.r_[cb,extra]))
        ct = top(co,20)
        for unbalanced in (False,True):
            vals=[]
            for row in ct:
                shard,loc=divmod(int(row),1000)
                passage=pack.vec[shard][pack.cum[shard][loc]:pack.cum[shard][loc+1]]
                value, diag=transport(encoded[f'c{i}'],passage,unbalanced)
                vals.append(value)
                transport_checks.append({'query':query['id'],'verse_id':int(store.ids[row]),'unbalanced':unbalanced,**diag})
            save('transport_unbalanced' if unbalanced else 'transport_balanced',np.array(vals),ct)
        # Validate unchanged canonical production rankings against preexisting cache.
        if query['split']=='development':
            old=read(ROOT/'local-benchmarks/mathematical-retrieval-v1/search-results.json')
            prev=next(q for q in old['queries'] if q['intent']==query['id'] and q['kind']=='formal')
            for name in ('compass','lantern','compass_unbalanced'):
                same=ranks[name][:10]==prev['methods'][name]['ids']
                checks.append({'query':query['id'],'method':name,'exact':same})
                assert same,(query['id'],name)
        original=[]
        if 'anchors_from' in query:
            for anchor in scenarios[query['anchors_from']]['anchors']:
                if anchor.endswith(':*'):
                    original += [v for ref,v in refs.items() if ref.startswith(anchor[:-1])]
                else:
                    assert anchor in refs,anchor
                    original.append(refs[anchor])
        pool=sorted(set(original)|{v for rank in ranks.values() for v in rank[:5]})
        np.random.default_rng(SEED+i).shuffle(pool)
        results.append({**query,'methods':ranks,'original_anchors':original,'pool':pool,
                        'candidate_counts':{'initial':len(cb),'colbert':len(extended),'graph_new':len(discovered),'control_new':len(extra)},
                        'candidate_ids':{'initial':store.ids[cb].tolist(),'colbert':store.ids[extended].tolist()}})
        review.append({**query,'passages':[{'verse_id':v,'reference':store.ref(v),'text':store.text(v)} for v in pool]})
        print(f'ranked {i+1}/{len(queries)} pool={len(pool)}',flush=True)
    write(OUT/'rankings.json',{'queries':results,'provenance':'Fixed offline methods; no relevance labels used.'})
    write(OUT/'review-pool.json',{'queries':review,'provenance':'Method/rank/score blinded; assistant review pending.'})
    write(OUT/'verification.json',{'canonical_cache_parity':checks,'transport':transport_checks})
    print('Pool complete:',sum(len(q['passages']) for q in review),'passage judgments needed',flush=True)


def score():
    result=read(OUT/'rankings.json')
    judgments=read(OUT/'assistant-judgments.json')
    assert judgments['provenance']=='assistant_text_review'
    marks=judgments['judgments']
    summary={}
    expanded=[]
    supplements=read(OUT/'supplement-pool.json')['queries'] if (OUT/'supplement-pool.json').exists() else {}
    for q in result['queries']:
        y=marks[q['id']]
        expected={str(v) for v in q['pool']} | {str(p['verse_id']) for p in supplements.get(q['id'],[])}
        assert set(y)==expected,q['id']
        for item in y.values():
            assert item['grade'] in (0,1,2) and item['reason'].strip()
        expanded.append({'id':q['id'],'query':q['query'],'split':q['split'],
                         'direct':[int(v) for v,j in y.items() if j['grade']==2],
                         'related':[int(v) for v,j in y.items() if j['grade']==1],
                         'reviewed_irrelevant':[int(v) for v,j in y.items() if j['grade']==0]})
    for split in ('development','challenge','all'):
        selected=[q for q in result['queries'] if split=='all' or q['split']==split]
        per={}
        for q in selected:
            y=marks[q['id']]
            ideal=sorted([2**j['grade']-1 for j in y.values()],reverse=True)[:5]
            discount=1/np.log2(np.arange(5)+2)
            idcg=float(np.dot(ideal,discount))
            per[q['id']]={}
            for name,rank in q['methods'].items():
                labels=np.array([y[str(v)]['grade'] for v in rank[:5]])
                per[q['id']][name]={'related5':float(np.mean(labels>=1)), 'direct5':float(np.mean(labels==2)),
                                    'ndcg5':float(np.dot(2**labels-1,discount)/idcg) if idcg else 0.,
                                    'original_anchor_hit5':float(bool(set(rank[:5])&set(q['original_anchors']))),
                                    'expanded_anchor_hit5':float(np.any(labels>=1))}
        summary[split]={'queries':len(selected),'methods':{},'per_query':per}
        for name in selected[0]['methods']:
            vals=[per[q['id']][name] for q in selected]
            delta=[per[q['id']][name]['ndcg5']-per[q['id']]['compass']['ndcg5'] for q in selected]
            summary[split]['methods'][name]={k:float(np.mean([v[k] for v in vals])) for k in vals[0]}
            summary[split]['methods'][name].update({'ndcg_delta':float(np.mean(delta)),
                                                   'ndcg_delta_ci95':interval(delta,[q['id'] for q in selected])})
    write(OUT/'expanded-anchors.json',{'provenance':'assistant_text_review','scope':'Complete pooled review, not exhaustive corpus relevance','queries':expanded})
    write(ROOT/'tool/search_anchors_v2.json',{
        'provenance':'assistant_text_review; NOT independent human judgments',
        'scope':'36 query-specific answer keys. Complete reviewed pool, not exhaustive corpus relevance. Evaluation only; never runtime rules.',
        'rubric':judgments['rubric'],'pool_sha256':judgments['pool_sha256'],
        'queries':[{'id':q['id'],'query':q['query'],'split':q['split'],
                    'anchors':[{'reference':j['reference'],'grade':j['grade'],'reason':j['reason']}
                               for j in marks[q['id']].values() if j['grade']>0],
                    'reviewed_nonanswers':[{'reference':j['reference'],'reason':j['reason']}
                                          for j in marks[q['id']].values() if j['grade']==0]}
                   for q in result['queries']]})
    write(OUT/'scored-results.json',{'provenance':'assistant_text_review; exploratory synthetic evaluation only','summary':summary})
    lines=['# Retrieval v2: assistant-reviewed offline results','',
           'All top-five passages are reviewed against actual text. These are assistant judgments, not independent reader accuracy.','']
    for split,data in summary.items():
        lines += [f'## {split}: {data["queries"]} queries','',
                  '| Method | Related P@5 | Direct P@5 | Pooled nDCG@5 | Delta vs Compass [95% exploratory] |',
                  '|---|---:|---:|---:|---|']
        for name,v in data['methods'].items():
            lo,hi=v['ndcg_delta_ci95']
            lines.append(f'| {name} | {v["related5"]:.3f} | {v["direct5"]:.3f} | {v["ndcg5"]:.3f} | {v["ndcg_delta"]:+.3f} [{lo:+.3f}, {hi:+.3f}] |')
        lines.append('')
    (OUT/'report.md').write_text('\n'.join(lines)+'\n','utf-8')
    print('Scored',len(result['queries']),'fully judged queries',flush=True)


if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--score',action='store_true')
    ap.add_argument('--out',type=Path,default=OUT,help='Fresh directory for a new run if code or inputs changed')
    args=ap.parse_args()
    OUT=args.out.resolve()
    with threadpool_limits(limits=4):
        score() if args.score else run()
