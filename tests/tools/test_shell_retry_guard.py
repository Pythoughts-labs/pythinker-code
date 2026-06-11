"""Tests for the restricted-profile retry hard-stop key normalization.

The retry guard counts verbatim command failures and hard-denies after
``MAX_IDENTICAL_FAILURES``. Keying on the raw string let a restricted agent
mint a fresh counter with trivial whitespace padding (``false`` vs ``false ``);
the key is whitespace-normalized so padding collapses while semantic variants
(quoting, flag order) stay distinct.
"""

from __future__ import annotations

from pythinker_code.tools.shell import MAX_IDENTICAL_FAILURES, Shell
from pythinker_code.tools.shell import _failure_key as failure_key


def test_failure_key_collapses_whitespace_padding():
    base = failure_key("false")
    assert failure_key("false ") == base
    assert failure_key(" false") == base
    assert failure_key("false\t") == base
    assert failure_key("false\n") == base
    assert failure_key("ls  -l   /tmp") == failure_key("ls -l /tmp")


def test_failure_key_preserves_semantic_variation():
    # Flag order is meaningful — distinct keys, so a genuinely different command
    # is not silently folded into another's failure count.
    assert failure_key("ls -l -a") != failure_key("ls -a -l")
    # Quoting changes argument grouping; keep it distinct.
    assert failure_key('echo "a b"') != failure_key("echo a b")


def test_record_failed_attempt_folds_padded_variants(shell_tool: Shell):
    # Three padded spellings of the same command must share one counter and
    # cross the cap, not mint three separate sub-cap counters.
    shell_tool._record_failed_attempt("false")
    shell_tool._record_failed_attempt("false ")
    shell_tool._record_failed_attempt("  false  ")

    assert shell_tool._failed_attempts == {"false": 3}
    assert shell_tool._failed_attempts["false"] >= MAX_IDENTICAL_FAILURES


def test_record_failed_attempt_keeps_distinct_commands_separate(shell_tool: Shell):
    shell_tool._record_failed_attempt("ls -l -a")
    shell_tool._record_failed_attempt("ls -a -l")

    assert shell_tool._failed_attempts == {"ls -l -a": 1, "ls -a -l": 1}
