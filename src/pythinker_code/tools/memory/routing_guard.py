"""Structural detector for memory writes that probably belong in a file.

A recurring failure mode: the user *corrects* a rule that lives in an
authoritative project file (a protocol/spec/config the agent reads), and the
agent — to satisfy the "write facts, not instructions" rule — rephrases the
correction as a "preference" and stores it in memory. The file stays stale, the
correction is silently lost, and memory bloats with directives.

The tool is blind to conversation context, so it cannot *know* whether a
governing file exists. It can only spot the structural shape of a correction and
*advise*. This module is that detector: pure, deterministic, no project
knowledge, no I/O. The tool layer appends a one-line nudge when a signal trips;
it never blocks, so false positives cost nothing but a sentence of output.
"""

from __future__ import annotations

import re

# A token that looks like a config/doc filename. High precision: if the entry
# names such a file, that file — not memory — is the source of truth.
_FILE_REF = re.compile(
    r"\b[\w./-]+\.(?:md|markdown|ya?ml|json|toml|ini|cfg|conf|txt|env)\b",
    re.IGNORECASE,
)

# Value-assignment grammar: a directive verb steering a number ("set ... to 100",
# "raise ... 12"). Bounded gap so it stays a local phrase, not a whole paragraph.
_DIRECTIVE_VERB = re.compile(
    r"\b(?:set|change|update|increase|decrease|raise|lower|bump|cap|adjust)\b[^.\n]{0,40}\d+",
    re.IGNORECASE,
)

# A limit/threshold word adjacent to a number, in either order. This is what
# catches the rephrased-as-preference evasion ("limit of 100").
_LIMIT_NUM = re.compile(
    r"\b(?:limit|max(?:imum)?|min(?:imum)?|threshold|cap|quota)\b[^.\n]{0,20}\d+"
    r"|\d+[^.\n]{0,20}\b(?:limit|max(?:imum)?|min(?:imum)?|threshold|cap|quota)\b",
    re.IGNORECASE,
)

# Prescriptive imperatives — the grammar of a rule rather than a fact.
_IMPERATIVE = re.compile(r"\b(?:always|never|must)\b", re.IGNORECASE)


def routing_signals(content: str) -> list[str]:
    """Return the structural signals tripped by ``content``, in stable order.

    ``"file_ref"`` — the entry names a config/doc file (that file is the likely
    source of truth). ``"directive"`` — the entry reads like a rule or a
    value-assignment rather than a standing fact. Empty list means nothing
    tripped. Order is deterministic (``file_ref`` before ``directive``) and each
    signal appears at most once, so callers can log it verbatim.
    """
    text = content or ""
    signals: list[str] = []
    if _FILE_REF.search(text):
        signals.append("file_ref")
    if _DIRECTIVE_VERB.search(text) or _LIMIT_NUM.search(text) or _IMPERATIVE.search(text):
        signals.append("directive")
    return signals
