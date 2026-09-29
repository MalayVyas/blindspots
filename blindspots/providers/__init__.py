"""Provider adapters: one module per model vendor, one shared result type.

Every adapter returns a `Completion` (base.py). Nothing above this layer
knows which vendor answered, which is what lets ADR-0008 swap the model
behind a role and change nothing else.
"""
