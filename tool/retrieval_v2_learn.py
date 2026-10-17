"""Fixed exploratory rank learning from development-only synthetic judgments."""
import sys
from pathlib import Path
import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import PolynomialFeatures, StandardScaler
from threadpoolctl import threadpool_limits
ROOT=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(ROOT/'tool'))
from mathematical_retrieval_experiment import Store, read, write, order, z, digest
OUT=ROOT/'local-benchmarks/retrieval-v2'


def run():
    store=Store()
    queries=read(OUT/'rankings.json')['queries']
    labels=read(OUT/'assistant-judgments.json')['judgments']
    enc=dict(np.load(OUT/'encoded.npz'))
    co=np.load(OUT/'exact-colbert.npy')
    features=[np.column_stack([z(store.Dstored @ enc[f'd{i}']),z(enc[f's{i}']),
                               z(co[i]),z(store.R @ enc[f'g{i}'])]) for i in range(len(queries))]
    train=[i for i,q in enumerate(queries) if q['split']=='development']
    test=[i for i,q in enumerate(queries) if q['split']=='challenge']
    assert not ({queries[i]['id'] for i in train}&{queries[i]['id'] for i in test})
    train_rows={i:np.array([store.row(int(v)) for v in labels[queries[i]['id']]]) for i in train}
    ys={i:np.array([j['grade'] for j in labels[queries[i]['id']].values()]) for i in train}
    outputs={i:{} for i in test}
    parameters={}
    for degree in (1,2):
        poly=PolynomialFeatures(degree=degree,include_bias=False)
        poly.fit(features[train[0]])
        scaler=StandardScaler().fit(np.concatenate([poly.transform(features[i][train_rows[i]]) for i in train]))
        dx,targets,weights=[],[],[]
        for i in train:
            x=scaler.transform(poly.transform(features[i][train_rows[i]]))
            y=ys[i]
            a,b=np.where(y[:,None]>y[None,:])
            if not len(a):
                continue
            delta=x[a]-x[b]
            dx.extend([delta,-delta]); targets.extend([np.ones(len(a)),np.zeros(len(a))])
            weights.extend([np.full(len(a),1/(2*len(a)))]*2)
        model=LogisticRegression(C=1,fit_intercept=False,solver='lbfgs',max_iter=2000)
        model.fit(np.concatenate(dx),np.concatenate(targets),sample_weight=np.concatenate(weights))
        assert max(model.n_iter_)<model.max_iter
        name='learned_linear' if degree==1 else 'learned_interactions'
        parameters[name]={'features':poly.get_feature_names_out(['dense','sparse','colbert','raw_genome']).tolist(),
                          'scaler_mean':scaler.mean_.tolist(),'scaler_scale':scaler.scale_.tolist(),
                          'coefficients':model.coef_[0].tolist(),'C':1,'iterations':int(model.n_iter_[0])}
        for i in test:
            scores=model.decision_function(scaler.transform(poly.transform(features[i])))
            outputs[i][name]=store.ids[order(scores,store.ids,20)].tolist()
            candidate=np.array([store.row(v) for v in queries[i]['candidate_ids']['initial']])
            outputs[i][name+'_candidate_pool']=store.ids[candidate[order(scores[candidate],store.ids[candidate],20)]].tolist()
    review=[]
    prior={q['id']:q['passages'] for q in read(OUT/'learned-review-pool.json')['queries']} if (OUT/'learned-review-pool.json').exists() else {}
    for i in test:
        q=queries[i]
        previous=prior.get(q['id'],[])
        new=sorted({v for rank in outputs[i].values() for v in rank[:5]}-{int(v) for v in labels[q['id']]}
                   -{p['verse_id'] for p in previous})
        np.random.default_rng(20261016+i).shuffle(new)
        review.append({'id':q['id'],'query':q['query'],'passages':previous+[
            {'verse_id':v,'reference':store.ref(v),'text':store.text(v)} for v in new]})
    write(OUT/'learned-rankings.json',{'train':[queries[i]['id'] for i in train],
                                     'test':[queries[i]['id'] for i in test], 'parameters':parameters,
                                     'labels_sha256':digest(OUT/'assistant-judgments.json'),
                                     'protocol_sha256':digest(ROOT/'docs/RETRIEVAL_V2_LEARNING_PROTOCOL.md'),
                                     'script_sha256':digest(Path(__file__)),
                                     'queries':[{'id':queries[i]['id'],'methods':outputs[i]} for i in test]})
    write(OUT/'learned-review-pool.json',{'queries':review,'provenance':'Method-blinded new passages; assistant review required.'})
    for q in review:
        print('\nQUERY',q['id'],q['query'])
        for j,p in enumerate(q['passages']):
            if j>=len(prior.get(q['id'],[])):
                print(f'{j} | {p["reference"]} | {p["text"]}')
    print('New judgments:',sum(len(q['passages']) for q in review))


if __name__=='__main__':
    with threadpool_limits(limits=4):
        run()
