"""Money representation tests: integer minor units, no floating point."""

from __future__ import annotations

from backend.money import format_minor, minor_to_major, rupees_to_minor, sum_minor


def test_rupees_to_minor_paise():
    assert rupees_to_minor(1) == 100
    assert rupees_to_minor(94_200) == 9_420_000
    assert rupees_to_minor(0) == 0


def test_minor_to_major_truncates():
    assert minor_to_major(9_420_000) == 94_200
    assert minor_to_major(150) == 1


def test_sum_is_exact_integer():
    values = [9_420_000, 100, 250, 999_999, 1]
    total = sum_minor(values)
    assert isinstance(total, int)
    assert total == sum(values)
    assert total == 9_420_000 + 100 + 250 + 999_999 + 1


def test_aggregation_has_no_float_error():
    # A float accumulation over 100_000 fractional-rupee values would drift;
    # integer minor units are exact by construction.
    values = [137 for _ in range(100_000)]
    total = sum_minor(values)
    assert total == 137 * 100_000
    assert isinstance(total, int)


def test_format_minor():
    assert format_minor(9_420_000) == "INR 94200.00"
    assert format_minor(100) == "INR 1.00"
    assert format_minor(0) == "INR 0.00"


def test_integer_types_enforced():
    import pytest

    with pytest.raises(TypeError):
        rupees_to_minor(1.5)  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        format_minor(1.0)  # type: ignore[arg-type]