import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from polymarket_clob_public import normalize_outcome_tokens, summarize_order_book


def test_normalize_outcome_tokens_extracts_yes_no_prices():
    market = {
        "outcomes": '["Yes", "No"]',
        "outcomePrices": '["0.62", "0.38"]',
        "clobTokenIds": '["yes-token", "no-token"]',
    }

    result = normalize_outcome_tokens(market)

    assert result["yesTokenId"] == "yes-token"
    assert result["noTokenId"] == "no-token"
    assert result["yesPrice"] == 62.0
    assert result["noPrice"] == 38.0
    assert len(result["outcomeTokens"]) == 2


def test_summarize_order_book_scores_public_depth_without_wallet_state():
    book = {
        "status": "OK",
        "bids": [{"price": "0.61", "size": "100"}, {"price": "0.60", "size": "50"}],
        "asks": [{"price": "0.64", "size": "80"}, {"price": "0.65", "size": "40"}],
    }

    summary = summarize_order_book(book)

    assert summary["clobStatus"] == "OK"
    assert summary["clobBestBid"] == 0.61
    assert summary["clobBestAsk"] == 0.64
    assert summary["clobSpread"] == 0.03
    assert summary["clobLiquidityUsd"] > 0
    assert 0 < summary["clobDepthScore"] <= 100


def test_summarize_order_book_keeps_errors_non_executable():
    summary = summarize_order_book({"status": "ERROR", "error": "timeout"})

    assert summary["clobStatus"] == "ERROR"
    assert summary["clobLiquidityUsd"] == 0.0
    assert summary["clobDepthScore"] == 0.0
