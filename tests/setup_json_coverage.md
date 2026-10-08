# Installer JSON query checks

Runner: `cargo test --offline --locked --release --test setup_json_cli`.
Every subprocess drives `setup-json` with actual JSON stdin or a fresh temp file.

| Rule | Saved assertions |
| --- | --- |
| Marketplace selection and missing root | `marketplace_roots_match_and_repeat`: exact Unicode/spaced path plus newline, two runs; missing name or list returns newline/status zero. |
| Codex installed list, Claude plugin and marketplace arrays | `membership_queries_match_installed_and_marketplace_shapes`: exact membership returns status zero, missing/empty returns one, no stdout/stderr. |
| Claude directory-backed registration | `claude_directory_registration_is_read_only`: exact path/source matches, different/absent returns one; bytes unchanged after every query. Missing file remains absent. Malformed file returns one and retains its bytes. |
| Empty/unknown command, missing/extra tokens per operation | `argument_and_document_rejections_are_observable`: status two for every shape. |
| Bad JSON, incompatible root/container | Same case: status one and no success output. |

All selectors are textual; numeric conversion and range policy are inapplicable.
Queries never mutate input or installed state. Each test owns fresh child stdin;
the sole file case owns and removes a unique process-scoped temporary directory.

Shell integration: `test_marketplace_shell_pipeline_uses_native_json_queries` in
`tests/test_rust_setup_integrations.py` feeds a fake native Codex list through the
real `prepare_codex_marketplace` pipeline. It asserts exact remove/add calls and
second-call cache reuse. The real Claude registry query matches/mismatches the
directory without changing its fixture bytes. No real native plugin install runs.
