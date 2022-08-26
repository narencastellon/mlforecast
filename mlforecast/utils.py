# AUTOGENERATED! DO NOT EDIT! File to edit: ../nbs/utils.ipynb.

# %% auto 0
__all__ = ['generate_daily_series', 'generate_prices_for_series', 'data_indptr_from_sorted_df', 'ensure_sorted',
           'backtest_splits']

# %% ../nbs/utils.ipynb 3
import random
from itertools import chain
from math import ceil, log10
from typing import Tuple

import numpy as np
import pandas as pd

# %% ../nbs/utils.ipynb 5
def generate_daily_series(
    n_series: int,
    min_length: int = 50,
    max_length: int = 500,
    n_static_features: int = 0,
    equal_ends: bool = False,
    static_as_categorical: bool = True,
    seed: int = 0,
) -> pd.DataFrame:
    """Generates `n_series` of different lengths in the interval [`min_length`, `max_length`].

    If `n_static_features > 0`, then each serie gets static features with random values.
    If `equal_ends == True` then all series end at the same date."""
    rng = np.random.RandomState(seed)
    random.seed(seed)
    series_lengths = rng.randint(min_length, max_length + 1, n_series)
    total_length = series_lengths.sum()
    n_digits = ceil(log10(n_series))

    dates = pd.date_range("2000-01-01", periods=max_length, freq="D").values
    uids = [
        [f"id_{i:0{n_digits}}"] * serie_length
        for i, serie_length in enumerate(series_lengths)
    ]
    if equal_ends:
        ds = [dates[-serie_length:] for serie_length in series_lengths]
    else:
        ds = [dates[:serie_length] for serie_length in series_lengths]
    y = np.arange(total_length) % 7 + rng.rand(total_length) * 0.5
    series = pd.DataFrame(
        {
            "unique_id": list(chain.from_iterable(uids)),
            "ds": list(chain.from_iterable(ds)),
            "y": y,
        }
    )
    for i in range(n_static_features):
        static_values = np.repeat(rng.randint(0, 100, n_series), series_lengths)
        series[f"static_{i}"] = static_values
        if static_as_categorical:
            series[f"static_{i}"] = series[f"static_{i}"].astype("category")
        if i == 0:
            series["y"] = series["y"] * (1 + static_values)
    series["unique_id"] = series["unique_id"].astype("category")
    series["unique_id"] = series["unique_id"].cat.as_ordered()
    series = series.set_index("unique_id")
    return series

# %% ../nbs/utils.ipynb 16
def generate_prices_for_series(
    series: pd.DataFrame, horizon: int = 7, seed: int = 0
) -> pd.DataFrame:
    rng = np.random.RandomState(0)
    unique_last_dates = series.groupby("unique_id")["ds"].max().nunique()
    if unique_last_dates > 1:
        raise ValueError("series must have equal ends.")
    if "product_id" not in series:
        raise ValueError("series must have a product_id column.")
    day_offset = pd.tseries.frequencies.Day()
    starts_ends = series.groupby("product_id")["ds"].agg([min, max])
    dfs = []
    for idx, (start, end) in starts_ends.iterrows():
        product_df = pd.DataFrame(
            {
                "product_id": idx,
                "price": rng.rand((end - start).days + 1 + horizon),
            },
            index=pd.date_range(start, end + horizon * day_offset, name="ds"),
        )
        dfs.append(product_df)
    prices_catalog = pd.concat(dfs).reset_index()
    return prices_catalog

# %% ../nbs/utils.ipynb 19
def data_indptr_from_sorted_df(df: pd.DataFrame) -> Tuple[np.ndarray, np.ndarray]:
    grouped = df.groupby("unique_id")
    sizes = grouped.size().values
    indptr = np.append(0, sizes.cumsum())
    data = df["y"].values
    return data, indptr


def ensure_sorted(df: pd.DataFrame) -> pd.DataFrame:
    df = df.set_index("ds", append=True)
    if not df.index.is_monotonic_increasing:
        df = df.sort_index()
    return df.reset_index("ds")

# %% ../nbs/utils.ipynb 20
def _split_info(
    data: pd.DataFrame, offset: int, window_size: int, freq: pd.offsets.BaseOffset
):
    # TODO: try computing this once and passing it to this fn
    last_dates = data.groupby("unique_id")["ds"].transform("max")
    train_ends = last_dates - offset * freq
    valid_ends = train_ends + window_size * freq
    valid_mask = data["ds"].gt(train_ends) & data["ds"].le(valid_ends)
    return pd.DataFrame({"train_end": train_ends, "is_valid": valid_mask})

# %% ../nbs/utils.ipynb 21
def backtest_splits(
    data, n_windows: int, window_size: int, freq: pd.offsets.BaseOffset
):
    for i in range(n_windows):
        offset = (n_windows - i) * window_size
        if isinstance(data, pd.DataFrame):
            splits = _split_info(data, offset, window_size, freq)
        else:
            splits = data.map_partitions(
                _split_info,
                offset=offset,
                window_size=window_size,
                freq=freq,
            )
        train_mask = data["ds"].le(splits["train_end"])
        train, valid = data[train_mask], data[splits["is_valid"]]
        yield splits.loc[splits["is_valid"], "train_end"], train, valid
