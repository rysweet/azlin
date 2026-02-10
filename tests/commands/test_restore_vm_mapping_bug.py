"""Test for VM/session mapping bug in azlin restore.

This test reproduces the critical bug where tmux sessions get assigned to wrong VMs.
"""

from pathlib import Path

from azlin.remote_exec import TmuxSession


def test_tmux_session_vm_name_preserved_through_cache():
    """Test that TmuxSession.vm_name is correctly preserved through cache serialization.

    BUG: When TmuxSession objects are cached and deserialized, their vm_name field
    might contain IP addresses instead of actual VM names, causing sessions to be
    restored to wrong VMs.
    """
    # Simulate tmux sessions collected from VMs
    sessions_vm1 = [
        TmuxSession(
            vm_name="10.0.0.1",  # This is how it comes from SSH (IP address)
            session_name="session1",
            windows=2,
            created_time="2024-01-01",
            attached=True,
        ),
        TmuxSession(
            vm_name="10.0.0.1",
            session_name="session2",
            windows=1,
            created_time="2024-01-01",
            attached=False,
        ),
    ]

    sessions_vm2 = [
        TmuxSession(
            vm_name="10.0.0.2",
            session_name="session3",
            windows=3,
            created_time="2024-01-01",
            attached=True,
        ),
    ]

    # Correctly mapped to VM names (this is what _collect_tmux_sessions does)
    tmux_by_vm = {
        "vm-1": sessions_vm1,  # Key is actual VM name
        "vm-2": sessions_vm2,
    }

    # Serialize and deserialize (simulating cache round-trip)
    for vm_name, sessions in tmux_by_vm.items():
        session_dicts = [s.to_dict() for s in sessions]

        # Deserialize
        restored_sessions = [TmuxSession.from_dict(d) for d in session_dicts]

        # BUG: After deserialization, restored_sessions still have vm_name="10.0.0.X"
        # but they're in the tmux_by_vm["vm-1"] list

        # When restore.py uses these sessions:
        for session in restored_sessions:
            # This assertion will FAIL because vm_name is IP, not actual VM name
            assert session.vm_name == vm_name, (
                f"BUG: Session vm_name is '{session.vm_name}' but should be '{vm_name}'. "
                f"This causes sessions to be restored to wrong VMs!"
            )


def test_restore_session_mapping_with_real_data_structure():
    """Test that restore correctly maps sessions to VMs using actual data flow.

    This reproduces the exact bug: sessions from VM-A appearing on VM-B.
    """
    from azlin.commands.restore import RestoreSessionConfig, TerminalType

    # Simulate the tmux_by_vm structure from _collect_tmux_sessions
    # Key: actual VM name, Value: list of TmuxSessions with vm_name=IP
    tmux_by_vm = {
        "amplifier": [
            TmuxSession(
                vm_name="10.0.0.13",
                session_name="amplifier",
                windows=2,
                created_time="",
                attached=True,
            ),
            TmuxSession(
                vm_name="10.0.0.13",
                session_name="rusty",
                windows=1,
                created_time="",
                attached=False,
            ),
        ],
        "seldon-dev": [
            TmuxSession(
                vm_name="10.0.0.14", session_name="azlin", windows=1, created_time="", attached=True
            ),
            TmuxSession(
                vm_name="10.0.0.14",
                session_name="wikigr",
                windows=2,
                created_time="",
                attached=False,
            ),
        ],
    }

    # Simulate VMs list
    class MockVM:
        def __init__(self, name, ip):
            self.name = name
            self.public_ip = None
            self.private_ip = ip

    vms = [
        MockVM("amplifier", "10.0.0.13"),
        MockVM("seldon-dev", "10.0.0.14"),
    ]

    # This is what restore.py does (lines 813-857)
    sessions = []
    for vm in vms:
        hostname = vm.public_ip or vm.private_ip
        vm_tmux_sessions = tmux_by_vm.get(vm.name, [])

        for tmux_sess in vm_tmux_sessions:
            session_config = RestoreSessionConfig(
                vm_name=vm.name,  # Using VM name from loop
                hostname=hostname,
                username="azureuser",
                ssh_key_path=Path("/tmp/test_key"),
                tmux_session=tmux_sess.session_name,  # Using session name from TmuxSession
                terminal_type=TerminalType.WINDOWS_TERMINAL,
            )
            sessions.append(session_config)

    # Verify correct mapping
    expected_sessions = [
        ("amplifier", "amplifier"),
        ("amplifier", "rusty"),
        ("seldon-dev", "azlin"),
        ("seldon-dev", "wikigr"),
    ]

    actual_sessions = [(s.vm_name, s.tmux_session) for s in sessions]

    assert actual_sessions == expected_sessions, (
        f"Session mapping is wrong!\nExpected: {expected_sessions}\nActual: {actual_sessions}"
    )
