# Experiments

`run_heldout.py` runs name-only, Valentine (COMA, Cupid, Similarity Flooding, Jaccard) and MergeGuard
on the dev scenario and the held-out scenarios.

```bash
mergeguard bench /tmp/mb --seed 7
python -c "from mergeguard.bench.generate import generate as g; g('/tmp/heldout_lending', seed=101, scenario='lending'); g('/tmp/heldout_cards', seed=101, scenario='cards')"
python experiments/run_heldout.py /tmp/mb /tmp/heldout_lending /tmp/heldout_cards results
```

Valentine needs NLTK data: `python -m nltk.downloader punkt_tab omw-1.4 stopwords wordnet`.

## Magneto (run on your machine)

Needs Hugging Face access for the small language model.

```bash
pip install bdi-kit
python -c "
from mergeguard.cards import load_side
from mergeguard.baselines import bdikit_predictions
from mergeguard.evaluate import evaluate
src = load_side('/tmp/heldout_cards/acquired', 'a', 'oracle'); tgt = load_side('/tmp/heldout_cards/acquirer', 't')
r = evaluate(bdikit_predictions(src, tgt, 'magneto_zs_bp'), '/tmp/heldout_cards/ground_truth.json', auto_accept=lambda m: m.target is not None)
print(r['target_accuracy'], r['harmful_auto_accepts'])"
```

The BDI-Kit adapter has not been tested in the sandbox; check the column names it returns.
