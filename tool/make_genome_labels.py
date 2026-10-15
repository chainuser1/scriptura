"""Build assets/genome_labels.json: plain labels for the 23 families and 568 genes (hand-editable afterwards).

  .venv\\Scripts\\python.exe -I tool/make_genome_labels.py [--keep-edits]
"""
import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FAMILIES = {
    'A': 'Form', 'B': 'Poetic craft', 'C': 'Imagery', 'D': 'Emotion', 'E': 'Human condition', 'F': 'Divine reference',
    'G': 'Moral texture', 'H': 'Time and place', 'I': 'Voice', 'J': 'Structure', 'K': 'How it is known',
    'L': 'Relationships', 'M': 'Bodily experience', 'N': 'Abstraction', 'O': 'Movement', 'P': 'Covenant',
    'Q': 'History and language', 'R': 'Doctrine', 'S': 'Salvation', 'T': 'Teaching and use', 'U': 'Range of meaning',
    'V': 'Precision', 'W': 'Moral and legal code',
}
DROP_FIRST = {'D': 'emotion', 'E': 'condition', 'G': 'moral', 'O': 'motion', 'M': 'phenom', 'P': 'covenant'}


def label(gene_id):
    code, rest = gene_id.split('_', 1)
    words = rest.split('_')
    if DROP_FIRST.get(code[0]) == words[0] and len(words) > 1:
        words = words[1:]
    text = ' '.join(words)
    return text[:1].upper() + text[1:]


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--keep-edits', action='store_true', help='keep labels already in the file that differ from the rule')
    a = ap.parse_args()
    genes = [l.strip() for l in (ROOT / 'generated-artifacts/engine-pack/retrieval/gene_ids.txt').read_text('utf-8').splitlines() if l.strip()]
    out = ROOT / 'assets' / 'genome_labels.json'
    old = json.loads(out.read_text('utf-8')) if (a.keep_edits and out.exists()) else {'genes': {}}
    data = {'families': FAMILIES, 'genes': {g: old['genes'].get(g) or label(g) for g in genes}}
    out.write_text(json.dumps(data, indent=1, ensure_ascii=False), 'utf-8')
    print(f'{len(genes)} gene labels, {len(FAMILIES)} families -> {out}')


if __name__ == '__main__':
    main()
