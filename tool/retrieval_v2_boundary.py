"""Read-only native semantic boundary probes; not a test of app-level routing."""
import ctypes
import json
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(ROOT/'tool'))
from mathematical_retrieval_experiment import read,write,digest
OUT=ROOT/'local-benchmarks/retrieval-v2'
QUERIES=[
    'What is the weather forecast for Chicago tomorrow?',
    'What is the current battery percentage of my phone?',
    'What is the balance in my bank account right now?',
    'Who won the football game yesterday?',
    'What is the tracking status of my package today?',
    'What is the password for my Wi-Fi router?',
    'What time is my next calendar appointment?',
    'qzxv trmbl qrrp'
]


def main():
    lib=ctypes.CDLL(str(ROOT/'engine/target/release/scripture_engine.dll'))
    lib.se_open.restype=ctypes.c_void_p
    lib.se_open.argtypes=[ctypes.c_char_p,ctypes.POINTER(ctypes.c_char_p)]
    lib.se_request.restype=ctypes.c_void_p
    lib.se_request.argtypes=[ctypes.c_void_p,ctypes.c_char_p]
    lib.se_free_string.argtypes=[ctypes.c_void_p]
    lib.se_close.argtypes=[ctypes.c_void_p]
    pack=ROOT/'generated-artifacts/engine-pack'
    m=read(pack/'manifest.json')
    cfg={'retrieval_dir':str(pack/'retrieval'),'head_npz':str(pack/'head.npz'),
         'encoder_model':str(pack/m['encoder_file']),'tokenizer_json':str(pack/'tokenizer.json'),
         'pack_dir':str(ROOT/'generated-artifacts/colbert-pack-v1'),
         'topics_db':str(ROOT/'generated-artifacts/topics-pack-v1/topics.db'),
         'profiles':m['profiles'],'default_profile':m['default_profile'],
         'fallback_without_thread':m['fallback_without_thread'],'identity':m['identity'],
         'threads':4,'volume_balance':.75}
    error=ctypes.c_char_p()
    handle=lib.se_open(json.dumps(cfg).encode(),ctypes.byref(error))
    assert handle,error.value
    results=[]
    try:
        for query in QUERIES:
            p=lib.se_request(handle,json.dumps({'op':'semantic','query':query,'profile':'compass','top_k':5}).encode())
            try:
                response=json.loads(ctypes.string_at(p))
            finally:
                lib.se_free_string(p)
            assert 'error' not in response,response
            results.append({'query':query,'expected':'No direct factual answer in this fixed scripture corpus',
                            'response':response})
    finally:
        lib.se_close(handle)
    write(OUT/'boundary-results.json',{'scope':'Native semantic endpoint only, not app routing or a calibrated OOD benchmark',
                                      'native_sha256':digest(ROOT/'engine/target/release/scripture_engine.dll'),
                                      'queries':results})
    print('Boundary probes:',len(results),'returned passages:',sum(bool(q['response'].get('hits')) for q in results))


if __name__=='__main__':
    main()
