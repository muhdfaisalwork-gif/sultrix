"""tests/test_truth_check_20261020.py

2026-10-20: the database said forex -54.33 while the MT5 account (50,000 deposited) said about -147: nothing compared the two. The truth check
compares the database result with the broker's balance minus deposits. Pinned: the broker figure, the OK / MISMATCH / NOT CHECKED judgement
with a small tolerance for swap, and that it works from a fake terminal.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

sys.path.insert(0, str(Path(__file__).parent.parent / "sultrix_audit"))
import truth_check as tc


class Deal:
    def __init__(self, type_, profit):
        self.type, self.profit = type_, profit


class FakeMT5:
    DEAL_TYPE_BALANCE = 2

    def __init__(self, balance, deals, account=True):
        self._balance, self._deals, self._account = balance, deals, account

    def account_info(self):
        class A:
            pass
        if not self._account:
            return None
        a = A()
        a.balance, a.equity = self._balance, self._balance - 2.3
        return a

    def history_deals_get(self, frm, to):
        return self._deals


def test_the_broker_realized_result_is_balance_minus_deposits():
    mt5 = FakeMT5(49854.81, [Deal(2, 50000.0), Deal(0, -10.0)])

    r = tc.forex_broker_result(mt5)

    assert r["realized"] == pytest.approx(-145.19) and r["deposits"] == 50000.0 and r["equity"] == pytest.approx(49852.51)


def test_an_unreadable_terminal_gives_none_not_a_guess():
    assert tc.forex_broker_result(FakeMT5(0, [], account=False)) is None
    assert tc.forex_broker_result(object()) is None


def test_the_judgement_catches_a_hole_like_the_one_of_october():
    assert tc.judge(-145.19, -145.06) == ("OK", 0.13)
    status, gap = tc.judge(-145.06, -54.33)                      # the database before the repair
    assert status == "MISMATCH" and gap == pytest.approx(90.73)
    assert tc.judge(None, -5.0) == ("NOT CHECKED", None) and tc.judge(-1.0, None) == ("NOT CHECKED", None)


def test_the_tolerance_allows_swap_but_not_a_real_gap():
    assert tc.judge(-100.0, -101.9)[0] == "OK" and tc.judge(-100.0, -103.0)[0] == "MISMATCH"
