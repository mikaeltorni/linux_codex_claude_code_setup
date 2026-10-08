# Native setup installation checks

Runner: `python3 -m pytest -q tests/test_native_setup_installation.py`.

| Contract | Executable assertions |
| --- | --- |
| Clean side-effect-free discovery | `test_unbuilt_component_listing_is_complete_and_side_effect_free`: shipped installer lists exactly the built list twice with Python/network traps, no target/home writes; changed defaults reject immediately without mutation. |
| Default JSON authority | `test_committed_listing_matches_native_defaults_and_digest`: saved rows equal Rust output, digest equals JSON bytes. |
| No implicit Python / preserve failed mutation | `test_missing_native_helper_fails_before_marketplace_mutation`: both defaults runners and catalog generation reject absent executables; populated catalog observed immediately after each failure. |
| Root-mode file ownership | `test_builder_preserves_invoker_toolchain_and_installs_via_target`: mock invoker Cargo validates existing custom environment; every installed ELF passes through target runner. |
| Clean Rust dependency | `test_builder_bootstraps_when_no_cargo_exists`: mock network/bootstrap, real installation copy, all ELFs asserted. |
| Failed compiler | `test_failed_build_installs_nothing`: exact failure status, no distribution/user outputs. |
| Native history lifecycle | `test_history_installs_native_engine_and_preserves_data_on_uninstall`: real installed wrapper merges independently expected history twice, migrates old managed engine, detects and uninstalls without touching histories. |

These installation helpers have no numeric operand contract. CLI arity/conversion
is already covered by retained Rust public suites. No package installation,
real bootstrap download, GUI or system action occurs. Each mutable case owns
fresh temporary source/home state. Real Cargo/test binaries are reused only as
copy sources; the clean-install path itself has none until its mocked build.
