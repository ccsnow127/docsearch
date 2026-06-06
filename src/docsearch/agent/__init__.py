"""A minimal coding-agent runtime, used in two roles.

A single generic director loop (``runtime.run_agent``) drives both:

  * the GENERATION agent — edits ``test_suite.py`` in a workspace until the
    ``measure`` feedback tool reports better pass_rate / coverage / mutation, and
  * the DEVELOPER agent — edits the harness code until the ``run_eval`` feedback
    tool reports a better aggregate outcome.

Both share the same architecture (the filesystem-as-state pattern): the filesystem is
both the agent's memory (AGENTS.md, the artifact files) and its action surface
(read/write/edit/grep/bash, confined to the workspace), and a single feedback
tool shows the agent its REAL output so it iterates on outcomes, not appearance.
"""
