# Installer Reserve policy checks

Run `python3 -m unittest discover -s tests -p test_codex_reserve_policy.py -v` from the repository root. Python 3.11+ and a native Codex executable are required; set `CODEX_CONFIG_TEST_BINARY` for another executable. Only configuration RPCs run, with temporary homes, no model turns or GUI effects.

| Rule | Executable case and independently expected observation |
| --- | --- |
| Fresh default home and idempotence | test_clean_home_and_repeat: bool false, mode 0600, repeated bytes identical. |
| Existing numbered/provider homes and separate profiles | test_accounts_profiles_and_comments: every flag false, model/approval/web_search and comments preserved; unrelated nondirectory ignored. |
| Unknown/missing/extra CLI arguments | test_rejections_preserve_existing_configuration: nonzero then identical populated config before each next rejection. |
| Invalid TOML | same rejection case: nonzero, original default and malformed variant bytes untouched. |
| Shared installer integration | test_installer_postflight: sourced postflight writes temporary home false and manifest names the hook. |

Text path operands have no numeric conversion/domain requirements. Generic argparse owns missing/extra/unknown argument validation; the operation validates all TOML before writing. Each independent test has a fresh temporary home.
