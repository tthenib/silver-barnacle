# research — experiments

Disposable exploratory code. May import from `/src`; `/src` may never import from here.

- `analysis/` — standalone reproducible analyses (committed, with generated output in `/results`)
- `notebooks/` — exploratory work
- `config/` — one config file per experiment ID, hashed and referenced in [EXPERIMENT_LOG.md](../EXPERIMENT_LOG.md)

Every experiment must be pre-registered before it touches validation or test data.
