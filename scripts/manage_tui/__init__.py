"""Interactive Docker manager TUI for the scraper stack.

Entry point lives in scripts/manage.py. This package holds the pieces:

    model        constants + environments.yaml manifest loader
    compose      parse compose YAML -> profile -> services map
    config_view  parse .env (masked) -> display summary
    commands     build_sequence(env, scope, action) -> list[Command]  (preview == exec)
    runner       async, gated subprocess sequence runner with cancel
    app          the Textual application
"""
