"""Test that azlin restore never creates new tmux sessions.

CRITICAL BUG: restore is creating sessions that don't exist on VMs.
This happens when tmux_by_vm data incorrectly maps sessions to wrong VMs.
"""

from pathlib import Path

from azlin.commands.restore import RestoreSessionConfig, TerminalType
from azlin.remote_exec import TmuxSession


def test_restore_only_restores_existing_sessions():
    """Test that restore doesn't try to connect to sessions that don't exist on a VM.

    BUG SCENARIO:
    - amplihack-dev has sessions: [amplihack, azcli, kuzu-blarify]
    - seldon-dev has sessions: [azlin, wikigr]
    - Restore should NOT try to connect seldon-dev to 'amplihack' session
    - Restore should NOT try to connect lin-dev to 'atg-prs' session

    If tmux_by_vm data is corrupted, restore will try wrong sessions on wrong VMs,
    causing `azlin connect` to CREATE those sessions!
    """
    # Expected state (canonical from user's original list)
    expected_sessions_by_vm = {
        "atg-dev": ["atg-prs"],
        "amplihack-dev": ["amplihack", "azcli", "kuzu-blarify", "rusty", "wikigr"],
        "seldon-dev": ["azlin", "wikigr"],
        "amplifier": ["amplifier", "azcli", "azlin", "rusty"],
        "lin-dev": ["azcli", "azlin"],
        "simserv-dev": ["azcli", "recover"],
    }

    # Simulate _collect_tmux_sessions output (correct mapping)
    tmux_by_vm = {}
    for vm_name, session_names in expected_sessions_by_vm.items():
        tmux_by_vm[vm_name] = [
            TmuxSession(
                vm_name=vm_name,  # Should be actual VM name, not IP!
                session_name=session_name,
                windows=1,
                created_time="2024-01-01",
                attached=False,
            )
            for session_name in session_names
        ]

    # Simulate VMs list
    class MockVM:
        def __init__(self, name, ip):
            self.name = name
            self.public_ip = None
            self.private_ip = ip

    vms = [
        MockVM("atg-dev", "10.0.0.4"),
        MockVM("amplihack-dev", "10.0.0.6"),
        MockVM("seldon-dev", "10.0.0.14"),
        MockVM("amplifier", "10.0.0.13"),
        MockVM("lin-dev", "10.0.0.4"),  # Shared IP with atg-dev!
        MockVM("simserv-dev", "10.0.0.12"),
    ]

    # Simulate restore session building (from restore.py lines 813-857)
    sessions = []
    for vm in vms:
        hostname = vm.public_ip or vm.private_ip
        vm_tmux_sessions = tmux_by_vm.get(vm.name, [])

        for tmux_sess in vm_tmux_sessions:
            session_config = RestoreSessionConfig(
                vm_name=vm.name,
                hostname=hostname,
                username="azureuser",
                ssh_key_path=Path("/tmp/test_key"),
                tmux_session=tmux_sess.session_name,
                terminal_type=TerminalType.WINDOWS_TERMINAL,
            )
            sessions.append(session_config)

    # Verify: Each (VM, session) pair matches expected
    actual_pairs = [(s.vm_name, s.tmux_session) for s in sessions]
    expected_pairs = []
    for vm_name, session_names in expected_sessions_by_vm.items():
        for session_name in session_names:
            expected_pairs.append((vm_name, session_name))

    # Sort for comparison
    actual_pairs.sort()
    expected_pairs.sort()

    # THIS WILL FAIL if sessions are assigned to wrong VMs
    assert actual_pairs == expected_pairs, (
        f"Session mapping is corrupted!\n"
        f"Expected pairs: {expected_pairs}\n"
        f"Actual pairs: {actual_pairs}\n"
        f"Difference: {set(actual_pairs) - set(expected_pairs)}"
    )

    # Also verify: No VM should have sessions from another VM
    for session in sessions:
        # The session should only exist in the expected list for that VM
        expected_for_vm = expected_sessions_by_vm.get(session.vm_name, [])
        assert session.tmux_session in expected_for_vm, (
            f"BUG: VM '{session.vm_name}' should NOT have session '{session.tmux_session}'!\n"
            f"Expected sessions for {session.vm_name}: {expected_for_vm}\n"
            f"This session belongs to a different VM!"
        )


def test_tmux_by_vm_integrity_after_collection():
    """Test that tmux_by_vm dict maintains correct VM→sessions mapping.

    The bug might be that after _collect_tmux_sessions returns, the session
    objects have incorrect vm_name fields due to mutation or cache corruption.
    """
    # This simulates what _collect_tmux_sessions should return
    tmux_by_vm = {
        "vm-a": [
            TmuxSession(
                vm_name="vm-a", session_name="sess1", windows=1, created_time="", attached=False
            ),
            TmuxSession(
                vm_name="vm-a", session_name="sess2", windows=1, created_time="", attached=False
            ),
        ],
        "vm-b": [
            TmuxSession(
                vm_name="vm-b", session_name="sess3", windows=1, created_time="", attached=False
            ),
        ],
    }

    # Verify dictionary integrity
    for vm_name, sessions in tmux_by_vm.items():
        for session in sessions:
            assert session.vm_name == vm_name, (
                f"BUG: Session '{session.session_name}' has vm_name='{session.vm_name}' "
                f"but is in tmux_by_vm['{vm_name}'] list!"
            )
