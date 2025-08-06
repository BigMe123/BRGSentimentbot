# Privacy and Fairness Audit

This guide illustrates how to run the project's differential privacy utilities and how to produce a simple bias report.

## Differential privacy example

```python
from sentiment_bot.privacy import dp_mechanism

@dp_mechanism(epsilon=5.0, delta=1e-5)
def mean(xs):
    return sum(xs) / len(xs)

print(mean([1, 2, 3]))
print(f"ε={mean.epsilon:.2f}, δ={mean.delta:.1e}")
```

Example output:

```
2.0
ε=1.10, δ=1.0e-05
```

## Bias report

Count the class imbalance in a CSV dataset:

```bash
python - <<'PY'
import pandas as pd
df = pd.read_csv("data.csv")
print(df['label'].value_counts(normalize=True))
PY
```

Example output:

```
positive    0.70
negative    0.30
Name: label, dtype: float64
```

This shows the dataset is 70% positive and 30% negative.

## CLI demo

Run the built-in privacy decorator demo:

```bash
poetry run bot privacy-demo
```

Which prints:

```
eps=1.10, delta=1.0e-05
```

Use these commands as starting points for auditing privacy and fairness.
