# BRGSentimentbot

Async sentiment and volatility bot featuring RSS and NewsAPI scraping,
transformer-based analysis and optional web interfaces.

> **Requires Python 3.11–3.13.**

## Quickstart

### Poetry
```bash
pip install -U poetry
poetry install --no-root
poetry run bot once
```

### Docker
```bash
docker build -t brg-bot .
docker run --rm brg-bot
```

### Devcontainer
A simple `devcontainer.json` is provided for VS Code Remote Containers.

## CLI Usage
```bash
poetry run bot live            # continuous mode
poetry run bot once            # single cycle
poetry run bot chat            # interactive REPL
poetry run bot rules           # list loaded rules
poetry run bot simulate        # run Monte Carlo simulation
poetry run bot serve           # start websocket server
poetry run bot web             # websocket + gradio GUI
```

## Architecture
```mermaid
graph TD
    A[Scheduler] --> B[Fetchers]
    B --> C[Analyzer]
    C --> D[Vector Store]
    D --> E[Chat Agent]
    C --> F[Rules]
    C --> G[WebSocket]
    C --> H[Gradio GUI]
```

## Research Methodology

### Forecasting Architecture
```mermaid
graph LR
    V[Volatility Series] -->|GAN| G[Generator]
    V --> D[Discriminator]
    G --> F[Forecast]
```

### Streaming Topology
```mermaid
graph TD
    K[Kafka] --> S[Spark Streaming]
    S --> M[Model]
    M --> K2[Kafka Out]
```

### Quantum Optimiser
```plantuml
@startuml
participant "QAOA" as Q
participant "Optimizer" as O
Q -> O: evaluate(cost)
O -> Q: new parameters
@enduml
```

### Causal Inference
The Bayesian module supports counterfactual queries by sampling from the
posterior predictive distribution and contrasting interventions.

### Privacy & Fairness
- Differential privacy decorator `dp_mechanism`
- Bias reports can be generated with templates in `docs/privacy_template.md`

## License

Proprietary License Agreement
