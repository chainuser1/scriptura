"""Golden token-ID cases for the native tokenizer (PLAN 6.1 step 2, Phase 2).

Encodes eight-language, RTL, accent, punctuation, emoji, whitespace and mixed-language strings with the pinned
tokenizer.json (the Rust `tokenizers` core the app will bind), and cross-checks against transformers' fast wrapper and
the slow SentencePiece tokenizer. Any disagreement is reported, not hidden. Writes IDs only (no scripture text).

  .venv\\Scripts\\python.exe -I tool/make_tokenizer_goldens.py [--out test/golden/tokenizer_ids.json]
"""
import argparse
import hashlib
import json
import sys
from pathlib import Path

from tokenizers import Tokenizer
from transformers import AutoTokenizer, XLMRobertaTokenizer

ROOT = Path(__file__).resolve().parent.parent
BASE = ROOT / '.artifact-staging' / 'import-application-v1' / 'extracted' / 'bge-m3-pinned'

CASES = {
    'english': ['faith', 'What does the Bible teach about forgiveness?', 'Who was Melchizedek?',
                'love your neighbor as yourself', "don't be afraid — I'm with you", 'Genesis 1:1', 'John 3:16-18',
                'hope; mercy; justice... and "truth"?'],
    'spanish': ['¿Qué dice la Biblia sobre el amor al prójimo?', 'el perdón y la misericordia', 'Señor, ten piedad'],
    'tagalog': ['Ano ang sinasabi ng kasulatan tungkol sa pagpapakumbaba?', 'pag-ibig at pananampalataya'],
    'cebuano': ['Unsa ang gitudlo sa Bibliya bahin sa pagpasaylo?', 'pagtuo ug paglaom'],
    'french': ['Que dit la Bible sur le pardon ?', "l'amour du prochain, à l'église"],
    'german': ['Was sagt die Bibel über Vergebung?', 'Gnade und Wahrheit, Größe und Maß'],
    'greek': ['Ἐν ἀρχῇ ἦν ὁ λόγος', 'τί ἐστιν ἀλήθεια;', 'ἀγάπη καὶ πίστις'],
    'hebrew': ['שלום עולם', 'בְּרֵאשִׁית בָּרָא אֱלֹהִים', 'מה אומר המקרא על סליחה?'],
    'mixed': ['faith y esperanza and אמונה', 'Bible — 聖經 — Библия', 'I feel anxious 🙏 about tomorrow'],
    'edge': ['a', 'A', ' leading and trailing space ', 'tabs\tand\nnewlines', 'double  space', 'ALL CAPS QUERY',
             'café naïve résumé', 'ﬁ ligature and Ⅷ numeral', '​ zero-width', '١٢٣ Arabic-Indic digits', '123 456',
             'x' * 600],
}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--out', default=str(ROOT / 'test' / 'golden' / 'tokenizer_ids.json'))
    a = ap.parse_args()

    raw = Tokenizer.from_file(str(BASE / 'tokenizer.json'))
    fast = AutoTokenizer.from_pretrained(BASE)
    slow = XLMRobertaTokenizer.from_pretrained(BASE)
    out, disagreements = [], []
    for group, texts in CASES.items():
        for t in texts:
            r = raw.encode(t, add_special_tokens=True).ids
            f = fast(t, add_special_tokens=True, truncation=False)['input_ids']
            s = slow(t, add_special_tokens=True, truncation=False)['input_ids']
            row = {'group': group, 'text': t if len(t) <= 80 else t[:77] + '...', 'text_len': len(t),
                   'text_sha256': hashlib.sha256(t.encode('utf-8')).hexdigest(), 'ids': r, 'n_tokens': len(r),
                   'fast_wrapper_equal': r == f, 'slow_sentencepiece_equal': r == s}
            if r != f or r != s:
                disagreements.append({'group': group, 'text': row['text'], 'raw_vs_fast': r == f, 'raw_vs_slow': r == s})
            out.append(row)
    meta = {
        'tokenizer_json_sha256': hashlib.sha256((BASE / 'tokenizer.json').read_bytes()).hexdigest(),
        'sentencepiece_model_sha256': hashlib.sha256((BASE / 'sentencepiece.bpe.model').read_bytes()).hexdigest(),
        'special_ids': {'<s>': raw.token_to_id('<s>'), '<pad>': raw.token_to_id('<pad>'),
                        '</s>': raw.token_to_id('</s>'), '<unk>': raw.token_to_id('<unk>')},
        'note': 'ids include <s> ... </s>; 600-char case exercises length only (no truncation applied)',
    }
    Path(a.out).write_text(json.dumps({'meta': meta, 'cases': out, 'disagreements': disagreements},
                                      ensure_ascii=False, indent=1), 'utf-8')
    print(f'{len(out)} cases; fast-wrapper mismatches: {sum(not r["fast_wrapper_equal"] for r in out)}; '
          f'slow-sentencepiece mismatches: {sum(not r["slow_sentencepiece_equal"] for r in out)}')
    for d in disagreements:
        print('  DISAGREE', d)
    print('specials', meta['special_ids'])
    return 0


if __name__ == '__main__':
    sys.exit(main())
