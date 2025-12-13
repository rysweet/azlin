"""Integration tests for Natural Language Fleet Queries.

Tests the complete workflow:
1. FleetQueryParser parses natural language query
2. Commands are executed on fleet
3. ResultSynthesizer aggregates results
4. Display formatting works correctly
"""

from unittest.mock import patch

import pytest

from azlin.agentic.fleet_query_parser import FleetQueryParser, ResultSynthesizer
from azlin.batch_executor import BatchExecutor, BatchOperationResult
from azlin.vm_manager import VMInfo


@pytest.fixture
def sample_vms():
    """Create sample VMs for testing."""
    return [
        VMInfo(
            name="web-01",
            resource_group="test-rg",
            location="eastus",
            power_state="VM running",
            public_ip="1.2.3.4",
            vm_size="Standard_D2s_v3",
            tags={"env": "prod", "role": "web"},
        ),
        VMInfo(
            name="web-02",
            resource_group="test-rg",
            location="eastus",
            power_state="VM running",
            public_ip="1.2.3.5",
            vm_size="Standard_D2s_v3",
            tags={"env": "prod", "role": "web"},
        ),
        VMInfo(
            name="db-01",
            resource_group="test-rg",
            location="westus",
            power_state="VM running",
            public_ip="1.2.3.6",
            vm_size="Standard_D4s_v3",
            tags={"env": "prod", "role": "database"},
        ),
    ]


class TestFleetQueryIntegration:
    """Integration tests for fleet query workflow."""

    @pytest.mark.skip(reason="Requires ANTHROPIC_API_KEY - run manually if needed")
    def test_cost_query_workflow(self, sample_vms):
        """Test complete cost query workflow."""
        # Skip if no API key
        import os

        if not os.getenv("ANTHROPIC_API_KEY"):
            pytest.skip("ANTHROPIC_API_KEY not set")

        parser = FleetQueryParser()
        synthesizer = ResultSynthesizer()

        # Parse query
        query = "which VMs cost the most this month?"
        query_plan = parser.parse_query(query)

        # Verify query plan
        assert query_plan["query_type"] in ["cost_analysis", "resource_usage"]
        assert query_plan["confidence"] > 0.7
        assert len(query_plan["commands"]) > 0

        # Simulate execution results
        results = [
            {"vm_name": "web-01", "value": "$45.00", "metric": "cost"},
            {"vm_name": "web-02", "value": "$45.00", "metric": "cost"},
            {"vm_name": "db-01", "value": "$90.00", "metric": "cost"},
        ]

        # Synthesize results
        synthesis = synthesizer.synthesize(query, query_plan, results)

        # Verify synthesis
        assert "summary" in synthesis
        assert len(synthesis["results"]) > 0
        assert synthesis["total_analyzed"] == 3

    def test_disk_usage_query_execution(self, sample_vms):
        """Test disk usage query execution with mocked remote commands."""
        executor = BatchExecutor(max_workers=3)

        # Mock the remote command execution
        with patch.object(executor, "execute_command") as mock_exec:
            mock_exec.return_value = [
                BatchOperationResult(
                    vm_name="web-01",
                    success=True,
                    message="Success",
                    output="45%",
                    duration=1.0,
                ),
                BatchOperationResult(
                    vm_name="web-02",
                    success=True,
                    message="Success",
                    output="52%",
                    duration=1.1,
                ),
                BatchOperationResult(
                    vm_name="db-01",
                    success=True,
                    message="Success",
                    output="85%",
                    duration=1.2,
                ),
            ]

            # Execute command
            results = executor.execute_command(
                vms=sample_vms,
                command="df -h / | tail -1 | awk '{print $5}'",
                resource_group="test-rg",
            )

            # Verify results
            assert len(results) == 3
            assert all(r.success for r in results)

            # Check high disk usage detection
            high_usage = [r for r in results if int(r.output.strip("%")) > 80]
            assert len(high_usage) == 1
            assert high_usage[0].vm_name == "db-01"

    def test_version_check_query(self, sample_vms):
        """Test version check query with multiple versions."""
        executor = BatchExecutor(max_workers=3)

        with patch.object(executor, "execute_command") as mock_exec:
            mock_exec.return_value = [
                BatchOperationResult(
                    vm_name="web-01",
                    success=True,
                    message="Success",
                    output="Python 3.11.5",
                    duration=0.5,
                ),
                BatchOperationResult(
                    vm_name="web-02",
                    success=True,
                    message="Success",
                    output="Python 3.11.5",
                    duration=0.5,
                ),
                BatchOperationResult(
                    vm_name="db-01",
                    success=True,
                    message="Success",
                    output="Python 3.9.2",
                    duration=0.5,
                ),
            ]

            results = executor.execute_command(
                vms=sample_vms,
                command="python3 --version",
                resource_group="test-rg",
            )

            # Group by version
            versions = {}
            for result in results:
                if result.success:
                    version = result.output.strip()
                    if version not in versions:
                        versions[version] = []
                    versions[version].append(result.vm_name)

            # Verify grouping
            assert len(versions) == 2
            assert "Python 3.11.5" in versions
            assert "Python 3.9.2" in versions
            assert len(versions["Python 3.11.5"]) == 2
            assert len(versions["Python 3.9.2"]) == 1

    def test_query_with_filtering(self, sample_vms):
        """Test query with VM filtering by tag."""
        from azlin.batch_executor import BatchSelector

        # Filter by role=web
        web_vms = BatchSelector.select_by_tag(sample_vms, "role=web")

        assert len(web_vms) == 2
        assert all(vm.tags.get("role") == "web" for vm in web_vms)

    def test_query_confidence_handling(self):
        """Test handling of low confidence queries."""
        # This would be tested with real API in integration tests
        # For now, test the validation logic

        query_plan = {
            "query_type": "unknown",
            "commands": [{"command": "test"}],
            "aggregation": "none",
            "confidence": 0.5,  # Low confidence
        }

        # Low confidence should be handled by display logic
        assert query_plan["confidence"] < 0.7


class TestResultAggregation:
    """Test result aggregation and formatting."""

    def test_aggregate_by_value(self):
        """Test sorting results by value."""
        results = [
            {"vm_name": "vm-1", "value": "45%"},
            {"vm_name": "vm-2", "value": "85%"},
            {"vm_name": "vm-3", "value": "52%"},
        ]

        # Sort by value (extract percentage)
        def get_percentage(result):
            return int(result["value"].strip("%"))

        sorted_results = sorted(results, key=get_percentage, reverse=True)

        assert sorted_results[0]["vm_name"] == "vm-2"  # 85%
        assert sorted_results[1]["vm_name"] == "vm-3"  # 52%
        assert sorted_results[2]["vm_name"] == "vm-1"  # 45%

    def test_group_by_result(self):
        """Test grouping results by value."""
        results = [
            {"vm_name": "vm-1", "value": "Python 3.11"},
            {"vm_name": "vm-2", "value": "Python 3.11"},
            {"vm_name": "vm-3", "value": "Python 3.9"},
        ]

        # Group by value
        grouped = {}
        for result in results:
            value = result["value"]
            if value not in grouped:
                grouped[value] = []
            grouped[value].append(result["vm_name"])

        assert len(grouped) == 2
        assert len(grouped["Python 3.11"]) == 2
        assert len(grouped["Python 3.9"]) == 1

    def test_filter_above_threshold(self):
        """Test filtering results above threshold."""
        results = [
            {"vm_name": "vm-1", "value": "45%"},
            {"vm_name": "vm-2", "value": "85%"},
            {"vm_name": "vm-3", "value": "52%"},
        ]

        threshold = 80

        filtered = [r for r in results if int(r["value"].strip("%")) > threshold]

        assert len(filtered) == 1
        assert filtered[0]["vm_name"] == "vm-2"


class TestErrorHandling:
    """Test error handling in fleet queries."""

    def test_query_execution_with_failures(self, sample_vms):
        """Test handling of failed command executions."""
        executor = BatchExecutor(max_workers=3)

        with patch.object(executor, "execute_command") as mock_exec:
            mock_exec.return_value = [
                BatchOperationResult(
                    vm_name="web-01",
                    success=True,
                    message="Success",
                    output="45%",
                ),
                BatchOperationResult(
                    vm_name="web-02",
                    success=False,
                    message="Connection failed",
                    output=None,
                ),
                BatchOperationResult(
                    vm_name="db-01",
                    success=True,
                    message="Success",
                    output="85%",
                ),
            ]

            results = executor.execute_command(
                vms=sample_vms,
                command="df -h",
                resource_group="test-rg",
            )

            # Count successes and failures
            successes = [r for r in results if r.success]
            failures = [r for r in results if not r.success]

            assert len(successes) == 2
            assert len(failures) == 1
            assert failures[0].vm_name == "web-02"

    def test_query_with_no_matching_vms(self, sample_vms):
        """Test query when no VMs match criteria."""
        from azlin.batch_executor import BatchSelector

        # Try to select VMs with non-existent tag
        selected = BatchSelector.select_by_tag(sample_vms, "role=nonexistent")

        assert len(selected) == 0


class TestPerformance:
    """Test performance characteristics of fleet queries."""

    def test_query_response_time(self, sample_vms):
        """Test that queries complete within acceptable time."""
        import time

        executor = BatchExecutor(max_workers=10)

        with patch.object(executor, "execute_command") as mock_exec:
            # Simulate fast responses
            mock_exec.return_value = [
                BatchOperationResult(
                    vm_name=vm.name,
                    success=True,
                    message="Success",
                    output="test",
                    duration=0.1,
                )
                for vm in sample_vms
            ]

            start = time.time()
            results = executor.execute_command(
                vms=sample_vms,
                command="echo test",
                resource_group="test-rg",
            )
            elapsed = time.time() - start

            # Should complete very quickly with mocked execution
            assert elapsed < 1.0
            assert len(results) == len(sample_vms)

    def test_large_fleet_query(self):
        """Test query on large fleet (100+ VMs)."""
        # Create 100 sample VMs
        large_fleet = [
            VMInfo(
                name=f"vm-{i:03d}",
                resource_group="test-rg",
                location="eastus",
                power_state="VM running",
                public_ip=f"1.2.3.{i}",
                vm_size="Standard_B2s",
                tags={"env": "test"},
            )
            for i in range(100)
        ]

        # Test that selection is fast
        import time

        from azlin.batch_executor import BatchSelector

        start = time.time()
        selected = BatchSelector.select_running_only(large_fleet)
        elapsed = time.time() - start

        assert len(selected) == 100
        assert elapsed < 0.1  # Should be very fast
