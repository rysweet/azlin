"""
Sample SSH configurations for testing.

This module provides sample SSH config files, keys, and related data
for testing SSH configuration and connection functionality.
"""

# ============================================================================
# SSH CONFIG FILES
# ============================================================================

SAMPLE_SSH_CONFIG = """
Host azlin-dev
    HostName 20.123.45.67
    User azureuser
    IdentityFile ~/.ssh/azlin_rsa
    StrictHostKeyChecking no
    UserKnownHostsFile /dev/null
    ServerAliveInterval 60
    ServerAliveCountMax 3
"""

SAMPLE_SSH_CONFIG_MULTIPLE_HOSTS = """
Host azlin-dev
    HostName 20.123.45.67
    User azureuser
    IdentityFile ~/.ssh/azlin_rsa
    StrictHostKeyChecking no

Host azlin-prod
    HostName 20.234.56.78
    User azureuser
    IdentityFile ~/.ssh/azlin_prod_rsa
    StrictHostKeyChecking yes

Host github.com
    User git
    IdentityFile ~/.ssh/github_rsa
"""

EXISTING_SSH_CONFIG = """
# Existing SSH configuration

Host myserver
    HostName 192.168.1.100
    User myuser
    IdentityFile ~/.ssh/id_rsa

Host another-server
    HostName server.example.com
    User admin
    Port 2222
"""


# ============================================================================
# SSH KEYS
# ============================================================================

SAMPLE_SSH_KEY_PRIVATE = """-----BEGIN OPENSSH PRIVATE KEY-----
b3BlbnNzaC1rZXktdjEAAAAABG5vbmUAAAAEbm9uZQAAAAAAAAABAAABlwAAAAdzc2gtcn
NhAAAAAwEAAQAAAYEAwVc3Qx1K8L8L4K4L4K4L4K4L4K4L4K4L4K4L4K4L4K4L4K4L4K4L
4K4L4K4L4K4L4K4L4K4L4K4L4K4L4K4L4K4L4K4L4K4L4K4L4K4L4K4L4K4L4K4L4K4L
4K4L4K4L4K4L4K4L4K4L4K4L4K4L4K4L4K4L4K4L4K4L4K4L4K4L4K4L4K4L4K4L4K4L
-----END OPENSSH PRIVATE KEY-----"""

SAMPLE_SSH_KEY_PUBLIC = "ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABgQDBVzdDHUrwvwvgrgvgrgvgrgvgrgvgrgvgrgvgrgvgrgvgrgvgrgvgrgvgrgvgrgvgrgvgrgvgrgvgrgvgrgvgrgvgrgvgrg azureuser@azlin"

SAMPLE_SSH_KEY_ED25519_PRIVATE = """-----BEGIN OPENSSH PRIVATE KEY-----
b3BlbnNzaC1rZXktdjEAAAAABG5vbmUAAAAEbm9uZQAAAAAAAAABAAAAMwAAAAtzc2gtZW
QyNTUxOQAAACBqL8vZ8x7K4L4L4K4L4K4L4K4L4K4L4K4L4K4L4K4LAAAA
-----END OPENSSH PRIVATE KEY-----"""

SAMPLE_SSH_KEY_ED25519_PUBLIC = (
    "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIGovy9nzHsrgvgvgrgvgrgvgrgvgrgvgrgvgrgvgrg azureuser@azlin"
)


# ============================================================================
# KNOWN HOSTS
# ============================================================================

SAMPLE_KNOWN_HOSTS = """
20.123.45.67 ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABgQC5K4L4K4L4K4L4K4L4K4L4K4L
github.com ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABgQC8vZ8x7K4L4K4L4K4L4K4L4K4L
"""


# ============================================================================
# AUTHORIZED KEYS
# ============================================================================

SAMPLE_AUTHORIZED_KEYS = """
ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABgQDBVzdDHUrwvwvgrgvgrgvgrgvgrg azureuser@azlin
ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIGovy9nzHsrgvgvgrgvgrgvgrgvgrg admin@workstation
"""


# ============================================================================
# SSH COMMAND OUTPUTS
# ============================================================================

SSH_KEYGEN_OUTPUT = """
Generating public/private rsa key pair.
Your identification has been saved in /home/user/.ssh/azlin_rsa
Your public key has been saved in /home/user/.ssh/azlin_rsa.pub
The key fingerprint is:
SHA256:abcdefghijklmnopqrstuvwxyz1234567890ABC azureuser@azlin
The key's randomart image is:
+---[RSA 3072]----+
|    .o.          |
|   o  o          |
|  . .  .         |
+----[SHA256]-----+
"""

SSH_CONNECTION_SUCCESS_OUTPUT = """
Welcome to Ubuntu 22.04.3 LTS (GNU/Linux 5.15.0-1049-azure x86_64)

 * Documentation:  https://help.ubuntu.com
 * Management:     https://landscape.canonical.com
 * Support:        https://ubuntu.com/advantage

Last login: Thu Oct  9 10:00:00 2024 from 1.2.3.4
"""

SSH_CONNECTION_TIMEOUT_OUTPUT = """
ssh: connect to host 20.123.45.67 port 22: Connection timed out
"""

SSH_CONNECTION_REFUSED_OUTPUT = """
ssh: connect to host 20.123.45.67 port 22: Connection refused
"""

SSH_HOST_KEY_VERIFICATION_FAILED = """
@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@
@    WARNING: REMOTE HOST IDENTIFICATION HAS CHANGED!     @
@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@
IT IS POSSIBLE THAT SOMEONE IS DOING SOMETHING NASTY!
Someone could be eavesdropping on you right now (man-in-the-middle attack)!
"""


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================


def create_ssh_config_entry(
    host: str = "azlin-dev",
    hostname: str = "20.123.45.67",
    user: str = "azureuser",
    identity_file: str = "~/.ssh/azlin_rsa",
    strict_host_checking: bool = False,
) -> str:
    """Create an SSH config entry with specified parameters.

    Args:
        host: SSH config host alias
        hostname: Actual hostname or IP address
        user: SSH username
        identity_file: Path to SSH private key
        strict_host_checking: Whether to enable strict host key checking

    Returns:
        SSH config entry as string
    """
    strict = "yes" if strict_host_checking else "no"
    return f"""
Host {host}
    HostName {hostname}
    User {user}
    IdentityFile {identity_file}
    StrictHostKeyChecking {strict}
    UserKnownHostsFile /dev/null
    ServerAliveInterval 60
    ServerAliveCountMax 3
"""


def create_ssh_key_pair(key_type: str = "rsa") -> tuple[str, str]:
    """Create a sample SSH key pair.

    Args:
        key_type: Type of SSH key ('rsa' or 'ed25519')

    Returns:
        Tuple of (private_key, public_key) as strings
    """
    if key_type == "ed25519":
        return (SAMPLE_SSH_KEY_ED25519_PRIVATE, SAMPLE_SSH_KEY_ED25519_PUBLIC)
    return (SAMPLE_SSH_KEY_PRIVATE, SAMPLE_SSH_KEY_PUBLIC)
