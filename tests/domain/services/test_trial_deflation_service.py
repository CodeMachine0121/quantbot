import numpy as np
import pytest

from quantbot.domain.services.trial_deflation_service import TrialDeflationService

HOURS_PER_YEAR = 365.0 * 24.0


def service() -> TrialDeflationService:
    return TrialDeflationService()


def test_the_standard_error_shrinks_with_more_data():
    one_year = service().standard_error(
        observation_count=int(HOURS_PER_YEAR), periods_per_year=HOURS_PER_YEAR
    )
    four_years = service().standard_error(
        observation_count=int(HOURS_PER_YEAR * 4), periods_per_year=HOURS_PER_YEAR
    )

    assert one_year == pytest.approx(1.0, abs=0.01)
    # 資料變四倍，標準誤減半
    assert four_years == pytest.approx(one_year / 2.0, rel=0.01)


def test_one_trial_needs_no_deflation():
    """只跑一次的話，「取最大值」這個動作沒有發生，所以沒有偏誤要扣。"""
    assert (
        service().expected_maximum_sharpe(
            trial_count=1,
            observation_count=int(HOURS_PER_YEAR),
            periods_per_year=HOURS_PER_YEAR,
        )
        == 0.0
    )


def test_more_trials_raise_the_bar():
    bars = [
        service().expected_maximum_sharpe(
            trial_count=count,
            observation_count=int(HOURS_PER_YEAR),
            periods_per_year=HOURS_PER_YEAR,
        )
        for count in (2, 10, 100, 1_000)
    ]

    assert bars == sorted(bars)
    # sqrt(2 ln N)：從 10 次到 1000 次只長了不到一倍，所以「多試一點」很划算，
    # 而那正是問題所在
    assert bars[3] / bars[1] < 2.0


def test_the_expected_maximum_matches_the_square_root_of_two_log_n():
    observation_count = int(HOURS_PER_YEAR)
    expected = service().expected_maximum_sharpe(
        trial_count=44,
        observation_count=observation_count,
        periods_per_year=HOURS_PER_YEAR,
    )

    error = service().standard_error(
        observation_count=observation_count, periods_per_year=HOURS_PER_YEAR
    )
    assert expected == pytest.approx(float(np.sqrt(2.0 * np.log(44))) * error)


def test_the_haircut_can_go_negative_and_that_is_the_point():
    haircut = service().haircut(
        1.2,
        trial_count=44,
        observation_count=int(HOURS_PER_YEAR),
        periods_per_year=HOURS_PER_YEAR,
    )

    assert haircut < 0.0


def test_illegal_inputs_are_rejected():
    with pytest.raises(ValueError, match="trial_count"):
        service().expected_maximum_sharpe(
            trial_count=0, observation_count=100, periods_per_year=HOURS_PER_YEAR
        )
    with pytest.raises(ValueError, match="observation_count"):
        service().standard_error(observation_count=1, periods_per_year=HOURS_PER_YEAR)
