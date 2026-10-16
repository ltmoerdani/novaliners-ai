"""Revenue domain plugin for the universal navigation pipeline (core/navigation).

Revenue fills three things core does not have: the signal reader (`signals.py`), the possibility
space (`space.py` + ontology/possibility/revenue.json), and the lifecycle/advisory hook (`paths.py`).
The five Revenue motions (ACQUISITION, REPRICING, EXPANSION, PARTNERSHIP, PAID_ACQUISITION) live as
PRIMITIVE motions in the strategy registry (ontology/route/strategies.json) — labels on the
strategy, not the definition of a Possible Path."""
