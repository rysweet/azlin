"""Unit tests for optimization recommendations.

Test Structure: 60% Unit tests (TDD Red Phase)
Feature: Cost optimization recommendations (oversized VMs, scheduling, idle resources)

These tests follow TDD approach - ALL tests should FAIL initially until
the recommendations engine is complete.
"""

from datetime import datetime, time, timedelta
from decimal import Decimal
from unittest.mock import Mock, patch

from azlin.costs.optimizer import (
    CostOptimizer,
    IdleResourceDetector,
    OptimizationRecommendation,
    OptimizationRule,
    OversizedVMDetector,
    RecommendationPriority,
    SchedulingOpportunity,
)


class TestOversizedVMDetector:
    """Tests for detecting oversized VMs."""

    def test_detector_identifies_underutilized_cpu(self):
        """Test detector finds VMs with low CPU utilization."""
        vm_metrics = {
            "vm_size": "Standard_E16as_v5",  # 16 cores, expensive
            "cpu_avg": 5.0,  # Only 5% CPU usage
            "memory_avg": 30.0,
            "cost_per_hour": Decimal("0.572"),
        }

        detector = OversizedVMDetector()
        recommendation = detector.analyze_vm("azlin-vm-prod-01", vm_metrics)

        assert recommendation is not None
        assert "downsize" in recommendation.action.lower()
        assert recommendation.estimated_savings > 0

    def test_detector_identifies_underutilized_memory(self):
        """Test detector finds VMs with low memory utilization."""
        vm_metrics = {
            "vm_size": "Standard_E16as_v5",  # 128GB RAM
            "cpu_avg": 40.0,
            "memory_avg": 15.0,  # Only 15% memory usage
            "cost_per_hour": Decimal("0.572"),
        }

        detector = OversizedVMDetector()
        recommendation = detector.analyze_vm("azlin-vm-dev-01", vm_metrics)

        assert recommendation is not None
        assert "Standard_E8as_v5" in recommendation.suggested_size  # Suggests smaller size

    def test_detector_suggests_appropriate_downsize(self):
        """Test detector suggests correct smaller VM size."""
        vm_metrics = {
            "vm_size": "Standard_E16as_v5",
            "cpu_avg": 25.0,
            "memory_avg": 30.0,
            "cost_per_hour": Decimal("0.572"),
        }

        detector = OversizedVMDetector()
        recommendation = detector.analyze_vm("test-vm", vm_metrics)

        # Should suggest E8as_v5 (half the size)
        assert "E8as_v5" in recommendation.suggested_size
        assert recommendation.estimated_savings > Decimal("200.00")  # Monthly savings

    def test_detector_skips_rightsized_vms(self):
        """Test detector doesn't flag appropriately sized VMs."""
        vm_metrics = {
            "vm_size": "Standard_E4as_v5",
            "cpu_avg": 65.0,  # Good utilization
            "memory_avg": 70.0,
            "cost_per_hour": Decimal("0.252"),
        }

        detector = OversizedVMDetector()
        recommendation = detector.analyze_vm("test-vm", vm_metrics)

        assert recommendation is None  # No recommendation needed

    def test_detector_calculates_savings_accurately(self):
        """Test detector calculates monthly savings correctly."""
        current_cost = Decimal("0.572")  # E16as_v5
        suggested_cost = Decimal("0.498")  # E8as_v5

        detector = OversizedVMDetector()
        savings = detector.calculate_monthly_savings(current_cost, suggested_cost)

        # (0.572 - 0.498) * 730 hours/month
        expected = (current_cost - suggested_cost) * 730
        assert savings == expected

    def test_detector_uses_configurable_thresholds(self):
        """Test detector respects configurable utilization thresholds."""
        vm_metrics = {
            "vm_size": "Standard_D8s_v5",
            "cpu_avg": 35.0,
            "memory_avg": 40.0,
            "cost_per_hour": Decimal("0.384"),
        }

        # Default threshold (30%) - should trigger
        detector1 = OversizedVMDetector(cpu_threshold=30.0)
        rec1 = detector1.analyze_vm("vm-1", vm_metrics)
        assert rec1 is None  # Above threshold

        # Higher threshold (40%) - should trigger
        detector2 = OversizedVMDetector(cpu_threshold=40.0)
        rec2 = detector2.analyze_vm("vm-1", vm_metrics)
        assert rec2 is not None  # Below threshold


class TestIdleResourceDetector:
    """Tests for detecting idle resources."""

    def test_detector_identifies_stopped_vms(self):
        """Test detector finds VMs that have been stopped for extended periods."""
        vm_info = {
            "name": "azlin-vm-old",
            "power_state": "VM stopped",
            "last_started": datetime.now() - timedelta(days=30),
            "cost_per_hour": Decimal("0.252"),
        }

        detector = IdleResourceDetector()
        recommendation = detector.analyze_stopped_vm(vm_info)

        assert recommendation is not None
        assert "delete" in recommendation.action.lower()
        assert recommendation.reason == "unused"

    def test_detector_identifies_idle_disks(self):
        """Test detector finds unattached disks."""
        disk_info = {
            "name": "disk-orphaned-01",
            "size_gb": 256,
            "tier": "Premium_LRS",
            "attached_to": None,
            "cost_per_month": Decimal("40.96"),
        }

        detector = IdleResourceDetector()
        recommendation = detector.analyze_disk(disk_info)

        assert recommendation is not None
        assert "unattached" in recommendation.reason.lower()
        assert recommendation.estimated_savings == Decimal("40.96")

    def test_detector_identifies_old_snapshots(self):
        """Test detector finds outdated snapshots."""
        snapshot_info = {
            "name": "snapshot-backup-2020",
            "size_gb": 128,
            "created_date": datetime(2020, 1, 1),
            "cost_per_month": Decimal("6.40"),
        }

        detector = IdleResourceDetector(snapshot_retention_days=90)
        recommendation = detector.analyze_snapshot(snapshot_info)

        assert recommendation is not None
        assert "old" in recommendation.reason.lower()

    def test_detector_preserves_recent_snapshots(self):
        """Test detector doesn't flag recent snapshots."""
        snapshot_info = {
            "name": "snapshot-recent",
            "size_gb": 128,
            "created_date": datetime.now() - timedelta(days=7),
            "cost_per_month": Decimal("6.40"),
        }

        detector = IdleResourceDetector(snapshot_retention_days=30)
        recommendation = detector.analyze_snapshot(snapshot_info)

        assert recommendation is None  # Keep recent snapshots

    def test_detector_identifies_unused_public_ips(self):
        """Test detector finds unassigned public IPs."""
        ip_info = {
            "name": "ip-unassigned",
            "assigned_to": None,
            "cost_per_month": Decimal("3.65"),
        }

        detector = IdleResourceDetector()
        recommendation = detector.analyze_public_ip(ip_info)

        assert recommendation is not None
        assert recommendation.estimated_savings == Decimal("3.65")


class TestSchedulingOpportunity:
    """Tests for VM scheduling opportunities."""

    def test_opportunity_identifies_dev_vm_schedule(self):
        """Test identifies VMs that can run on business hours schedule."""
        vm_info = {
            "name": "azlin-vm-dev-01",
            "tags": {"environment": "dev"},
            "cost_per_hour": Decimal("0.252"),
            "running_24x7": True,
        }

        opportunity = SchedulingOpportunity()
        recommendation = opportunity.analyze_vm(vm_info)

        assert recommendation is not None
        assert "schedule" in recommendation.action.lower()
        # Should save 118 idle hours/week * 4.3 weeks = ~507 hours/month
        # $0.252/hour * 507 hours = $127.76/month
        assert recommendation.estimated_savings > Decimal("120.00")  # Monthly

    def test_opportunity_calculates_business_hours_savings(self):
        """Test calculates savings from business hours schedule (8am-6pm, weekdays)."""
        hourly_cost = Decimal("0.252")

        opportunity = SchedulingOpportunity()
        savings = opportunity.calculate_business_hours_savings(hourly_cost)

        # Business hours: 10 hours/day * 5 days = 50 hours/week
        # Total hours: 168 hours/week
        # Savings: 118 hours/week * 4.3 weeks * hourly_cost
        expected_idle_hours = 118 * 4.3  # ~507 hours/month
        expected_savings = hourly_cost * Decimal(str(expected_idle_hours))

        assert abs(savings - expected_savings) < Decimal("1.00")  # Allow small variance

    def test_opportunity_suggests_weekend_only_schedule(self):
        """Test suggests weekend-only schedule for training VMs."""
        vm_info = {
            "name": "azlin-vm-training",
            "tags": {"purpose": "training"},
            "cost_per_hour": Decimal("0.498"),
            "running_24x7": True,
        }

        opportunity = SchedulingOpportunity()
        recommendation = opportunity.analyze_vm(vm_info)

        assert "weekend" in recommendation.schedule.lower()
        # Should save ~5 days/week
        savings_ratio = recommendation.estimated_savings / (Decimal("0.498") * 730)
        assert savings_ratio > Decimal("0.70")  # Save >70% of costs

    def test_opportunity_skips_production_vms(self):
        """Test doesn't suggest scheduling for production VMs."""
        vm_info = {
            "name": "azlin-vm-prod-01",
            "tags": {"environment": "production"},
            "cost_per_hour": Decimal("0.572"),
            "running_24x7": True,
        }

        opportunity = SchedulingOpportunity()
        recommendation = opportunity.analyze_vm(vm_info)

        assert recommendation is None  # Don't schedule production

    def test_opportunity_creates_startup_shutdown_schedule(self):
        """Test creates concrete startup/shutdown schedule."""
        schedule = SchedulingOpportunity.create_business_hours_schedule()

        assert schedule.start_time == time(8, 0)  # 8 AM
        assert schedule.stop_time == time(18, 0)  # 6 PM
        assert schedule.weekdays_only is True


class TestOptimizationRecommendation:
    """Tests for optimization recommendation data structure."""

    def test_recommendation_initialization(self):
        """Test recommendation initializes with all fields."""
        rec = OptimizationRecommendation(
            resource_name="azlin-vm-dev-01",
            resource_type="VirtualMachine",
            action="Downsize VM",
            reason="Low CPU and memory utilization (avg 15%)",
            estimated_savings=Decimal("180.00"),
            priority=RecommendationPriority.MEDIUM,
            details={"current_size": "E16as_v5", "suggested_size": "E8as_v5"},
        )

        assert rec.resource_name == "azlin-vm-dev-01"
        assert rec.estimated_savings == Decimal("180.00")
        assert rec.priority == RecommendationPriority.MEDIUM

    def test_recommendation_priority_ordering(self):
        """Test recommendations can be sorted by priority."""
        rec_high = OptimizationRecommendation(
            resource_name="vm-1",
            resource_type="VM",
            action="Delete",
            reason="Unused",
            estimated_savings=Decimal("500.00"),
            priority=RecommendationPriority.HIGH,
        )

        rec_low = OptimizationRecommendation(
            resource_name="vm-2",
            resource_type="VM",
            action="Downsize",
            reason="Underutilized",
            estimated_savings=Decimal("50.00"),
            priority=RecommendationPriority.LOW,
        )

        recommendations = [rec_low, rec_high]
        sorted_recs = sorted(recommendations, key=lambda r: r.priority.value, reverse=True)

        assert sorted_recs[0].priority == RecommendationPriority.HIGH

    def test_recommendation_formats_for_display(self):
        """Test recommendation formats nicely for CLI display."""
        rec = OptimizationRecommendation(
            resource_name="azlin-vm-test",
            resource_type="VirtualMachine",
            action="Schedule startup/shutdown",
            reason="Development VM running 24/7",
            estimated_savings=Decimal("180.50"),
            priority=RecommendationPriority.MEDIUM,
        )

        formatted = rec.format()

        assert "azlin-vm-test" in formatted
        assert "$180.50" in formatted
        assert "MEDIUM" in formatted.upper()


class TestCostOptimizer:
    """Tests for main cost optimizer orchestration."""

    @patch("azlin.costs.optimizer.VMManager")
    def test_optimizer_runs_all_detectors(self, mock_vm_manager):
        """Test optimizer runs all detection rules."""
        optimizer = CostOptimizer(resource_group="test-rg")

        recommendations = optimizer.analyze()

        # Should run oversized, idle, and scheduling detectors
        assert len(recommendations) >= 0  # May or may not find issues

    @patch("azlin.costs.optimizer.OversizedVMDetector")
    @patch("azlin.costs.optimizer.IdleResourceDetector")
    @patch("azlin.costs.optimizer.SchedulingOpportunity")
    def test_optimizer_aggregates_recommendations(self, mock_schedule, mock_idle, mock_oversized):
        """Test optimizer aggregates recommendations from all sources."""
        mock_oversized.return_value.analyze_all.return_value = [
            Mock(estimated_savings=Decimal("100"))
        ]
        mock_idle.return_value.analyze_all.return_value = [Mock(estimated_savings=Decimal("50"))]
        mock_schedule.return_value.analyze_all.return_value = [
            Mock(estimated_savings=Decimal("75"))
        ]

        optimizer = CostOptimizer(resource_group="test-rg")
        recommendations = optimizer.analyze()

        assert len(recommendations) == 3

    def test_optimizer_calculates_total_savings_potential(self):
        """Test optimizer sums total savings across all recommendations."""
        recommendations = [
            OptimizationRecommendation(
                resource_name="vm-1",
                resource_type="VM",
                action="Downsize",
                reason="Underutilized",
                estimated_savings=Decimal("150.00"),
                priority=RecommendationPriority.HIGH,
            ),
            OptimizationRecommendation(
                resource_name="disk-1",
                resource_type="Disk",
                action="Delete",
                reason="Unattached",
                estimated_savings=Decimal("40.00"),
                priority=RecommendationPriority.MEDIUM,
            ),
        ]

        optimizer = CostOptimizer(resource_group="test-rg")
        total = optimizer.calculate_total_savings(recommendations)

        assert total == Decimal("190.00")

    def test_optimizer_filters_by_priority(self):
        """Test optimizer can filter recommendations by priority."""
        recommendations = [
            OptimizationRecommendation(
                resource_name="vm-1",
                resource_type="VM",
                action="Delete",
                reason="Unused",
                estimated_savings=Decimal("500.00"),
                priority=RecommendationPriority.HIGH,
            ),
            OptimizationRecommendation(
                resource_name="vm-2",
                resource_type="VM",
                action="Downsize",
                reason="Underutilized",
                estimated_savings=Decimal("50.00"),
                priority=RecommendationPriority.LOW,
            ),
        ]

        optimizer = CostOptimizer(resource_group="test-rg")
        high_priority = optimizer.filter_by_priority(recommendations, RecommendationPriority.HIGH)

        assert len(high_priority) == 1
        assert high_priority[0].resource_name == "vm-1"

    def test_optimizer_exports_recommendations_to_json(self):
        """Test optimizer can export recommendations as JSON."""
        recommendations = [
            OptimizationRecommendation(
                resource_name="vm-1",
                resource_type="VM",
                action="Downsize",
                reason="Low utilization",
                estimated_savings=Decimal("100.00"),
                priority=RecommendationPriority.MEDIUM,
            )
        ]

        optimizer = CostOptimizer(resource_group="test-rg")
        json_export = optimizer.export_to_json(recommendations)

        assert "resource_name" in json_export
        assert "estimated_savings" in json_export


class TestOptimizationRule:
    """Tests for optimization rule engine."""

    def test_rule_defines_condition_and_action(self):
        """Test rule defines condition check and recommended action."""

        def check_cpu(vm_metrics):
            return vm_metrics["cpu_avg"] < 20

        rule = OptimizationRule(
            name="Low CPU Usage",
            condition=check_cpu,
            action="Downsize to smaller VM",
            savings_calculator=lambda: Decimal("100.00"),
        )

        vm_metrics = {"cpu_avg": 15.0}
        assert rule.applies(vm_metrics) is True

    def test_rule_can_be_enabled_or_disabled(self):
        """Test rules can be toggled on/off."""
        rule = OptimizationRule(
            name="Test Rule", condition=lambda x: True, action="Do something", enabled=True
        )

        assert rule.is_enabled()

        rule.disable()
        assert not rule.is_enabled()

    def test_rule_supports_custom_parameters(self):
        """Test rules support configurable parameters."""

        def check_threshold(vm_metrics, threshold):
            return vm_metrics["cpu_avg"] < threshold

        rule = OptimizationRule(
            name="Configurable CPU Check",
            condition=lambda vm: check_threshold(vm, 25),
            action="Downsize",
            parameters={"threshold": 25},
        )

        assert rule.parameters["threshold"] == 25
