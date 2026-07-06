"""Legacy backend module.

The ``BaseBackend`` / ``CUDABackend`` / ``MLXBackend`` abstraction previously
defined here was never wired into the training or inference paths and has been
removed. Active training backends live in :mod:`backends.swift_backend`;
inference backends live in :mod:`api.inference.backends`.
"""
