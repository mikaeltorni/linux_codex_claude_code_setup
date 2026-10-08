# Rust Reserve policy public checks

Build with `cargo build --offline --locked --release`, then run
`python3 -m unittest discover -s tests -p test_rust_reserve_policy.py -v`.
`CODEX_CONFIG_TEST_BINARY` selects the native Codex used solely for config RPCs.
Every case uses a fresh temporary home; no model turn or live config is touched.

| Contract | Saved executable assertions |
| --- | --- |
| Fresh default, private home/config, repeat and cleanup | `test_native_clean_home_repeat_and_permissions`: false opt-out, modes 0700/0600, identical bytes/output, no staging dirs. |
| Accounts/providers/profiles, symlink home, ignored files | `test_native_all_homes_profiles_symlink_and_comments`: each config has independently expected model/approval/features, comments and mode 0640; symlink/file retained. |
| Empty CLI, missing required keys/values, unknown/extra tokens | `test_bad_arguments_and_invalid_batch_preserve_populated_files`: status 2 followed immediately by populated config bytes after each rejection. |
| Invalid TOML in later home | Same case: status 1 and BOTH earlier valid config and malformed input unchanged. |
| RPC error, missing change, malformed response, early native EOF | `test_rpc_errors_and_false_ack_leave_original_untouched`: each status 1 followed immediately by original bytes and staging cleanup. |
| Concurrent original write | `test_concurrent_write_is_preserved`: explicit refusal, concurrent bytes retained, cleanup. |
| Actual shell postflight uses new Rust policy | `test_installer_postflight_uses_rust`: isolated native prefix, false flag, no Python invocation in shell source. |
| Help/equals syntax and unavailable native editor | `test_help_equals_paths_and_missing_executable`: help status zero without mutation, missing binary nonzero without mutation/leftover staging, equals form edits false. |
| Native editor never acknowledges | `test_rpc_wait_is_bounded`: production 30-second timeout, original bytes retained, child/staging cleanup. |

Operands are text paths; numeric conversion/range validation is inapplicable.
RPC waiting is bounded in production; native errors are injected at the external
process boundary, while success cases drive the real installed native editor.
The old Python policy remains a reference, with its retained four public tests.
Normal successful Rust output is empty, replacing incidental Python entry traces;
the installer consumes exit status and the TOML result, never those traces.
