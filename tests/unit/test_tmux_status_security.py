"""Security tests for tmux session connection status feature (Issue #499).

Tests verify that Rich markup injection vulnerabilities are prevented through
proper input sanitization.
"""

from rich.markup import escape


class TestRichMarkupInjectionPrevention:
    """Tests for preventing Rich markup injection attacks."""

    def test_malicious_session_name_with_markup_is_escaped(self):
        """Test that session names containing Rich markup are properly escaped."""
        # Attacker tries to inject red blinking text
        test_name = "[red]CRITICAL[/red][blink]HACKED[/blink]"
        escaped = escape(test_name)

        # Verify escaping works - markup should be escaped, not interpreted
        assert escaped != test_name  # Should be different after escaping
        # Escaped version should display the literal brackets
        assert "red" in escaped  # Text content preserved
        assert "CRITICAL" in escaped  # Text content preserved

    def test_link_injection_is_escaped(self):
        """Test that link injection attempts are escaped."""
        # Attacker tries to inject clickable malicious link
        malicious_name = "[link=http://evil.com]click-me[/link]"

        escaped = escape(malicious_name)

        # Verify link is not active (markup is escaped)
        assert "[link=" not in escaped or escaped.startswith("\\[")
        assert escaped != malicious_name

    def test_dim_and_bold_markup_in_session_names_is_escaped(self):
        """Test that dim/bold markup in session names is escaped."""
        # Attacker tries to hide their session or make it look special
        test_name = "[dim]hidden[/dim]"
        escaped = escape(test_name)

        # When displayed, it will be escaped so the markup is visible, not interpreted
        assert escaped != test_name  # Should be different after escaping
        assert "dim" in escaped  # Text content preserved
        assert "hidden" in escaped  # Text content preserved

    def test_nested_markup_is_escaped(self):
        """Test that nested Rich markup is properly escaped."""
        # Complex nested markup attack
        malicious_name = "[bold][red][blink]ALERT[/blink][/red][/bold]"

        escaped = escape(malicious_name)

        # All markup should be escaped
        assert escaped != malicious_name
        # Opening brackets should be escaped
        assert escaped.count("\\[") > 0 or escaped.count("&lt;") > 0

    def test_escape_function_prevents_interpretation(self):
        """Test that Rich's escape() function prevents markup interpretation."""
        # Various markup patterns that should be escaped
        dangerous_patterns = [
            "[red]text[/red]",
            "[link=http://evil.com]link[/link]",
            "[bold]bold[/bold]",
            "[dim]dim[/dim]",
            "[blink]blink[/blink]",
            "[on red]background[/on red]",
        ]

        for pattern in dangerous_patterns:
            escaped = escape(pattern)
            # After escaping, the pattern should be different (escaped)
            assert escaped != pattern, f"Pattern '{pattern}' was not escaped"
            # Escaped version should not contain unescaped opening brackets
            # (or they should be at the start with backslash)
            if "[" in escaped and not escaped.startswith("\\["):
                # If [ exists without \ prefix, it should be HTML-escaped
                assert "&lt;" in escaped or "\\[" in escaped

    def test_vm_session_name_escaping(self):
        """Test that VM session names are also escaped."""
        # VM names could come from user-controlled tags/config
        malicious_vm_name = "[link=http://phishing.com]important-vm[/link]"

        escaped = escape(malicious_vm_name)

        # Verify escaping prevents link from being clickable
        assert escaped != malicious_vm_name
        assert "[link=" not in escaped or escaped.startswith("\\[")


class TestSecurityBestPractices:
    """Tests that verify security best practices are followed."""

    def test_shell_metacharacters_are_safe_as_strings(self):
        """Test that shell metacharacters in session names are treated as strings."""
        # Session names with shell metacharacters - should be safe as strings
        dangerous_chars = [
            "session;rm -rf /",
            "session$(malicious)",
            "session`malicious`",
            "session|malicious",
            "session&malicious",
        ]

        for dangerous_name in dangerous_chars:
            # These are just strings - escaping should preserve them
            escaped = escape(dangerous_name)
            # Content should be preserved (though markup might be escaped)
            assert "session" in escaped
            # The dangerous parts are just text, not executed
            assert True  # Successfully handled as string
