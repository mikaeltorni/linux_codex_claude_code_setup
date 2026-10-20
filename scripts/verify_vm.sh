#!/usr/bin/env bash
# Run on the test VM: install twice into an isolated home, then probe all aliases.
set -euo pipefail
vm_source_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
vm_test_home="${VM_TEST_HOME:-$vm_source_root/tmp/vm-verification-$(date +%Y%m%d-%H%M%S)-$$}"
vm_cargo_home="${CARGO_HOME:-$HOME/.cargo}"
vm_rustup_home="${RUSTUP_HOME:-$HOME/.rustup}"
vm_test_path="$vm_cargo_home/bin:/usr/local/bin:/usr/bin:/bin"
mkdir -p "$vm_test_home"
printf 'VM host: %s\nTest home: %s\n' "$(hostname)" "$vm_test_home"
uname -sm
for vm_iteration in 1 2; do
  printf 'Installation pass %s\n' "$vm_iteration"
  env HOME="$vm_test_home" PATH="$vm_test_path" \
    CARGO_HOME="$vm_cargo_home" RUSTUP_HOME="$vm_rustup_home" \
    bash "$vm_source_root/install.sh" --barebones \
      --codex-instances 3 --claude-instances 2
done
for vm_command in codex claude cx1 cx2 cx3 cc1 cc2; do
  printf 'Checking %s\n' "$vm_command"
  env HOME="$vm_test_home" PATH="$vm_test_home/.local/bin:$vm_test_path" \
    "$vm_test_home/.local/bin/$vm_command" --version
done
cmp "$vm_source_root/target/release/agent-instances" \
  "$vm_test_home/.local/libexec/linux_codex_claude_code_setup/agent-instances"
for vm_directory in .codex .codex-account-2 .codex-account-3 .claude .claude-account-2; do
  test -d "$vm_test_home/$vm_directory"
done
test ! -e "$vm_test_home/projects/agent_command_center"
test ! -e "$vm_test_home/projects/programming_prompts"
env HOME="$vm_test_home" "$vm_test_home/.local/bin/agent-instances" list
printf 'VM installation and all seven version probes passed. Evidence home: %s\n' "$vm_test_home"
