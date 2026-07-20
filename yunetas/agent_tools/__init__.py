"""
The agent-facing deploy tools.

These used to live in ``$YUNETAS_BASE/tools/agent/`` and ship inside the
.deb/.rpm, while the CLI that drives them shipped on PyPI. One tool, two
release channels, two cadences — so a CLI upgrade could hand a flag to a
script from an older SDK and fail with "unrecognized arguments", and a fix to
a script needed a full SDK release to reach anyone.

They are modules of the CLI now, versioned and released with it.
"""
