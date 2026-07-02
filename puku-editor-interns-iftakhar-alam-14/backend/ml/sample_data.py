"""
sample_data.py: tiny synthetic dataset generator.

We don't want this project to depend on a network download (no sklearn.datasets.fetch_*),
so we generate a small classification dataset from scratch.

This module exposes a single public function:
    load_dataset() -> (X_train, X_test, y_train, y_test, feature_names, target_names)

The dataset is a 2D synthetic "blobs" problem (3 classes) — small enough to train
in <1s but realistic enough to exercise the full pipeline.
"""
from typing import Tuple, List

import numpy as np


def load_dataset(
    n_samples: int = 300,
    n_features: int = 4,
    n_classes: int = 3,
    test_size: float = 0.2,
    random_state: int = 42,
) -> Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, List[str], List[str]]:
    """
    Generate a small classification dataset by sampling 3 isotropic Gaussian blobs.

    Returns:
        X_train, X_test  : numpy arrays of shape (n_samples * (1 - test_size), n_features)
        y_train, y_test  : numpy arrays of integer class labels
        feature_names    : list[str] of human-readable feature names
        target_names     : list[str] of human-readable class names
    """
    rng = np.random.default_rng(random_state)

    samples_per_class = n_samples // n_classes
    # Each class has its own centroid, spaced apart so they're easy to separate
    centroids = rng.uniform(low=-5.0, high=5.0, size=(n_classes, n_features))

    X_list, y_list = [], []
    for class_idx, centroid in enumerate(centroids):
        X_class = rng.normal(loc=centroid, scale=1.0, size=(samples_per_class, n_features))
        y_class = np.full(samples_per_class, class_idx, dtype=int)
        X_list.append(X_class)
        y_list.append(y_class)

    X = np.vstack(X_list)
    y = np.concatenate(y_list)

    # Shuffle the rows so train/test split is i.i.d.
    perm = rng.permutation(len(y))
    X, y = X[perm], y[perm]

    # Stratified-ish split (just take the first chunk for test, the rest for train)
    n_test = int(len(y) * test_size)
    X_test, y_test = X[:n_test], y[:n_test]
    X_train, y_train = X[n_test:], y[n_test:]

    feature_names = [f"feature_{i}" for i in range(n_features)]
    target_names = [f"class_{i}" for i in range(n_classes)]

    return X_train, X_test, y_train, y_test, feature_names, target_names
