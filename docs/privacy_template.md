# Privacy and Fairness Audit

## Differential Privacy Settings

The sentiment model was trained using the **DP‑SGD** algorithm from
`diffprivlib`.  Training ran for 5 epochs over 250 000 examples with the
following privacy budget:

| Parameter | Value |
|-----------|-------|
| Epsilon (ϵ) | 2.5 |
| Delta (δ)   | 1e‑5 |
| Noise multiplier | 1.1 |
| Gradient clipping norm | 1.0 |

These parameters provide a balance between privacy and model utility.  The
values were computed using the moments accountant method as implemented in
`diffprivlib`.

## Bias and Fairness Metrics

To understand disparate impact, the model was evaluated on a held‑out dataset
with demographic annotations for gender and race.  We recorded the following
metrics (values shown are absolute differences between groups):

* **Demographic parity difference:** 0.03
* **Equal opportunity difference:** 0.02
* **Sentiment F1‑score range:** 0.89–0.91 across groups

## Findings and Mitigation Steps

Initial analysis revealed slightly lower recall for negative sentiment on
articles referencing female subjects.  We mitigated this by augmenting the
training data with additional negative samples and by tuning the classification
threshold, reducing the parity gaps listed above.

## Reproducibility and References

1. **Data preprocessing:** `python scripts/preprocess.py --config configs/dp.yml`
2. **DP‑SGD training:** `python scripts/train.py --dp-epsilon 2.5 --dp-delta 1e-5`
3. **Fairness evaluation:** `python scripts/fairness.py --dataset data/validation.json`

Methodology references:

* C. Dwork et al., “The algorithmic foundations of differential privacy,” 2014.
* IBM `diffprivlib` – <https://github.com/IBM/differential-privacy-library>
* AIF360 fairness metrics – <https://aif360.mybluemix.net/>

These steps and references allow the audit to be reproduced and verified.
