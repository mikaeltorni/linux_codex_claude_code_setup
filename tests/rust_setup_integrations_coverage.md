# Rust setup integration repair checks

Runner: `python3 -m pytest -q tests/test_rust_setup_integrations.py
tests/test_claude_installation.py tests/test_programming_prompt_verification.py
tests/test_opencode_integration.py tests/test_status_bar_ownership.py`.

| Contract | Actual public-interface assertions |
| --- | --- |
| Runtime ELF resolution independent of Cargo | `test_compiled_defaults_are_usable_without_cargo_on_path`: real tab-separated catalog and ELF header, PATH contains only system commands. |
| Provider selection consumes Rust and preserves user selection file | `test_provider_status_line_uses_rust_and_retains_saved_fields`: both provider shell callers produce selected model/used-token array; fake Python refuses launch; selection JSON immediately unchanged. |
| Standalone Claude install still resolves defaults helper | `test_claude_install_never_reuses_binary_outside_target_home`: fake curl/Claude only, install succeeds without executing inherited host Claude; account settings helper remains real. |
| Verifier resolves its actual loader dependencies | `test_verifier_uses_current_defaults_without_generic_source`: real Rust defaults against fresh copies; none succeeds and missing/stale/retired/malformed cases fail. |
| Worktree-aware owning dependency discovery | Existing status-bar selections and ACC launch family assertions now read live siblings from Git common directory. |

These shell helpers accept no raw numeric operands. Retained defaults tests own
CLI shape/domain validation. Status-line operations are read-only and seeded
with explicit selections; their immediate unchanged JSON assertion protects
against accidental migration while querying. Native installer clients are
mocked at process boundaries; no network install, GUI or real runtime launch.
