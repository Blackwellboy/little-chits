"""The Experiment Lab (research plan R1): pre-registered, blinded, resumable multi-seed runs with a statistical report.

    python -m chits.lab run protocol.yaml --out runs/my-experiment
    python -m chits.lab resume runs/my-experiment
    python -m chits.lab analyze runs/my-experiment [--unblind]

A protocol (JSON, or YAML when PyYAML is installed) names the arms, seeds, days, island and the interventions every
arm gets on the same day. Before the first tick the lab writes a manifest (the protocol, its fingerprint, the code
commit) and seals which hidden label (A, B, ...) is which arm. Runs are stored under their labels only, so analysis
can be done blind; `--unblind` checks the seal before it names the arms.

Arms may think on instinct or a model whose exact `BrainConfig` dictionary is sealed into the protocol fingerprint.
A model arm is refused unless the protocol says `allow_models: true` AND the environment has CHITS_LAB_ALLOW_MODELS=1:
runs on the owner's GPUs need the owner's go-ahead. Model arms run strict and lockstep: no instinct stand-in.
"""
