import pandas as pd
import pytest

from quantbot.domain.services.walk_forward_service import (
    WalkForwardFold,
    WalkForwardService,
)


def make_index(bar_count: int) -> pd.DatetimeIndex:
    return pd.date_range("2026-01-01", periods=bar_count, freq="1h", tz="UTC")


def test_a_single_split_cuts_at_the_given_fraction():
    fold = WalkForwardService().split(make_index(100), in_sample_fraction=0.7)

    assert len(fold.in_sample) == 70
    assert len(fold.out_of_sample) == 30


def test_the_two_halves_never_overlap():
    """樣本內外重疊一根，樣本外就不再是樣本外了，而那在區間表上看不出來。"""
    fold = WalkForwardService().split(make_index(100))

    assert fold.in_sample.max() < fold.out_of_sample.min()
    assert set(fold.in_sample) & set(fold.out_of_sample) == set()


def test_an_overlapping_fold_cannot_be_constructed_at_all():
    index = make_index(10)

    with pytest.raises(ValueError, match="樣本外必須完全在樣本內之後"):
        WalkForwardFold(in_sample=index[:6], out_of_sample=index[4:])


def test_an_empty_half_is_rejected():
    index = make_index(10)

    with pytest.raises(ValueError, match="都不能是空的"):
        WalkForwardFold(in_sample=index[:0], out_of_sample=index)


@pytest.mark.parametrize("fraction", [0.0, 1.0, -0.1, 1.5])
def test_an_illegal_fraction_is_rejected(fraction):
    with pytest.raises(ValueError, match="in_sample_fraction"):
        WalkForwardService().split(make_index(100), in_sample_fraction=fraction)


def test_too_little_data_to_split_is_an_error():
    with pytest.raises(ValueError, match="切不出兩段"):
        WalkForwardService().split(make_index(1))


def test_rolling_folds_grow_the_window_and_each_has_its_own_out_of_sample():
    folds = WalkForwardService().folds(make_index(400), fold_count=3)

    assert len(folds) == 3
    lengths = [len(fold.in_sample) + len(fold.out_of_sample) for fold in folds]
    assert lengths == sorted(lengths)
    # 錨定式：每一折的樣本內都從同一個起點開始
    assert all(fold.in_sample.min() == folds[0].in_sample.min() for fold in folds)
    # 每一折的樣本外都不同
    assert len({fold.out_of_sample.max() for fold in folds}) == 3


def test_too_little_data_for_the_requested_fold_count_is_an_error():
    with pytest.raises(ValueError, match="切不出"):
        WalkForwardService().folds(make_index(5), fold_count=4)
