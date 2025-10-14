"""Cost tracking and estimation module.

This module provides cost tracking and estimation for Azure VMs:
- Calculate cost estimates based on VM size and uptime
- Show per-VM and total costs
- Support date range filtering
- Pretty formatting with rich tables

Pricing is approximate and based on Azure pay-as-you-go rates.
For exact costs, use Azure Cost Management.
"""

import json
import logging
import subprocess
from dataclasses import dataclass
from typing import List, Optional, Dict
from datetime import datetime, timedelta
from decimal import Decimal

from azlin.vm_manager import VMManager, VMInfo, VMManagerError

logger = logging.getLogger(__name__)


class CostTrackerError(Exception):
    """Raised when cost tracking operations fail."""
    pass


@dataclass
class VMCostEstimate:
    """Cost estimate for a single VM."""
    vm_name: str
    vm_size: str
    power_state: str
    hourly_rate: Decimal
    hours_running: Decimal
    estimated_cost: Decimal
    region: str
    created_time: Optional[str] = None

    def is_running(self) -> bool:
        """Check if VM is currently running."""
        return "running" in self.power_state.lower()


@dataclass
class CostSummary:
    """Summary of costs across multiple VMs."""
    total_cost: Decimal
    total_vms: int
    running_vms: int
    stopped_vms: int
    estimates: List[VMCostEstimate]
    date_range: Optional[tuple] = None

    def get_monthly_estimate(self) -> Decimal:
        """Get monthly cost estimate for currently running VMs."""
        monthly_cost = Decimal('0')
        hours_per_month = Decimal('730')  # Average hours per month

        for estimate in self.estimates:
            if estimate.is_running():
                monthly_cost += estimate.hourly_rate * hours_per_month

        return monthly_cost


class CostTracker:
    """Track and estimate Azure VM costs.

    This class provides:
    - VM cost estimation based on size and uptime
    - Per-VM cost breakdowns
    - Total cost summaries
    - Date range filtering
    """

    # VM hourly pricing (approximate, in USD)
    # Based on Azure Pay-As-You-Go pricing for Linux VMs in East US
    VM_PRICING = {
        'Standard_B1s': Decimal('0.0104'),
        'Standard_B1ms': Decimal('0.0207'),
        'Standard_B2s': Decimal('0.0416'),
        'Standard_B2ms': Decimal('0.0832'),
        'Standard_B4ms': Decimal('0.166'),
        'Standard_D2s_v3': Decimal('0.096'),
        'Standard_D4s_v3': Decimal('0.192'),
        'Standard_D8s_v3': Decimal('0.384'),
        'Standard_D16s_v3': Decimal('0.768'),
        'Standard_D32s_v3': Decimal('1.536'),
        'Standard_E2s_v3': Decimal('0.126'),
        'Standard_E4s_v3': Decimal('0.252'),
        'Standard_E8s_v3': Decimal('0.504'),
        'Standard_F2s_v2': Decimal('0.085'),
        'Standard_F4s_v2': Decimal('0.169'),
        'Standard_F8s_v2': Decimal('0.338'),
    }

    @classmethod
    def estimate_vm_cost(
        cls,
        vm: VMInfo,
        from_date: Optional[datetime] = None,
        to_date: Optional[datetime] = None
    ) -> VMCostEstimate:
        """Estimate cost for a single VM.

        Args:
            vm: VM information
            from_date: Start date for cost calculation (default: VM creation)
            to_date: End date for cost calculation (default: now)

        Returns:
            VMCostEstimate object

        Raises:
            CostTrackerError: If cost estimation fails
        """
        # Get hourly rate for VM size
        hourly_rate = cls._get_hourly_rate(vm.vm_size or 'Unknown')

        # Calculate hours running
        hours_running = cls._calculate_hours_running(
            vm,
            from_date,
            to_date
        )

        # Calculate estimated cost
        estimated_cost = hourly_rate * hours_running

        return VMCostEstimate(
            vm_name=vm.name,
            vm_size=vm.vm_size or 'Unknown',
            power_state=vm.power_state,
            hourly_rate=hourly_rate,
            hours_running=hours_running,
            estimated_cost=estimated_cost,
            region=vm.location,
            created_time=vm.created_time
        )

    @classmethod
    def estimate_costs(
        cls,
        resource_group: str,
        from_date: Optional[datetime] = None,
        to_date: Optional[datetime] = None,
        include_stopped: bool = True
    ) -> CostSummary:
        """Estimate costs for all VMs in a resource group.

        Args:
            resource_group: Resource group name
            from_date: Start date for cost calculation
            to_date: End date for cost calculation
            include_stopped: Include stopped VMs in summary

        Returns:
            CostSummary object

        Raises:
            CostTrackerError: If cost estimation fails
        """
        try:
            # List VMs in resource group
            vms = VMManager.list_vms(resource_group, include_stopped=include_stopped)
            vms = VMManager.filter_by_prefix(vms, "azlin")

            if not vms:
                return CostSummary(
                    total_cost=Decimal('0'),
                    total_vms=0,
                    running_vms=0,
                    stopped_vms=0,
                    estimates=[],
                    date_range=(from_date, to_date) if from_date or to_date else None
                )

            # Calculate cost for each VM
            estimates = []
            total_cost = Decimal('0')
            running_vms = 0
            stopped_vms = 0

            for vm in vms:
                estimate = cls.estimate_vm_cost(vm, from_date, to_date)
                estimates.append(estimate)
                total_cost += estimate.estimated_cost

                if estimate.is_running():
                    running_vms += 1
                else:
                    stopped_vms += 1

            return CostSummary(
                total_cost=total_cost,
                total_vms=len(vms),
                running_vms=running_vms,
                stopped_vms=stopped_vms,
                estimates=estimates,
                date_range=(from_date, to_date) if from_date or to_date else None
            )

        except VMManagerError as e:
            raise CostTrackerError(f"Failed to estimate costs: {e}")

    @classmethod
    def _get_hourly_rate(cls, vm_size: str) -> Decimal:
        """Get hourly rate for VM size.

        Args:
            vm_size: Azure VM size

        Returns:
            Hourly rate in USD
        """
        # Return known rate or estimate based on size
        if vm_size in cls.VM_PRICING:
            return cls.VM_PRICING[vm_size]

        # Estimate based on naming patterns
        if 'B1' in vm_size:
            return Decimal('0.02')
        elif 'B2' in vm_size:
            return Decimal('0.04')
        elif 'B4' in vm_size:
            return Decimal('0.16')
        elif 'D2' in vm_size:
            return Decimal('0.10')
        elif 'D4' in vm_size:
            return Decimal('0.20')
        elif 'D8' in vm_size:
            return Decimal('0.40')
        elif 'E2' in vm_size:
            return Decimal('0.13')
        elif 'E4' in vm_size:
            return Decimal('0.25')
        elif 'F2' in vm_size:
            return Decimal('0.09')
        elif 'F4' in vm_size:
            return Decimal('0.17')
        else:
            # Default estimate for unknown sizes
            logger.warning(f"Unknown VM size: {vm_size}, using default rate")
            return Decimal('0.10')

    @classmethod
    def _calculate_hours_running(
        cls,
        vm: VMInfo,
        from_date: Optional[datetime],
        to_date: Optional[datetime]
    ) -> Decimal:
        """Calculate hours a VM has been running.

        Args:
            vm: VM information
            from_date: Start date
            to_date: End date

        Returns:
            Number of hours as Decimal
        """
        # Use current time if to_date not specified
        end_time = to_date or datetime.now()

        # Use VM creation time if from_date not specified
        if from_date:
            start_time = from_date
        elif vm.created_time:
            try:
                # Parse ISO format timestamp
                start_time = datetime.fromisoformat(
                    vm.created_time.replace('Z', '+00:00')
                )
                # Convert to naive datetime for calculation
                start_time = start_time.replace(tzinfo=None)
            except Exception as e:
                logger.debug(f"Failed to parse created_time: {e}")
                # Assume 1 hour if we can't determine start time
                return Decimal('1')
        else:
            # If no creation time available, assume 1 hour
            logger.debug(f"No creation time for VM {vm.name}, assuming 1 hour")
            return Decimal('1')

        # Make end_time naive if it has timezone info
        if hasattr(end_time, 'tzinfo') and end_time.tzinfo:
            end_time = end_time.replace(tzinfo=None)

        # Calculate time difference
        time_diff = end_time - start_time

        # Convert to hours
        hours = Decimal(str(time_diff.total_seconds() / 3600))

        # Ensure positive value
        if hours < 0:
            hours = Decimal('0')

        return hours

    @classmethod
    def format_cost_table(
        cls,
        summary: CostSummary,
        by_vm: bool = False
    ) -> str:
        """Format cost summary as a table.

        Args:
            summary: Cost summary
            by_vm: Show per-VM breakdown

        Returns:
            Formatted table string
        """
        lines = []

        # Header
        lines.append("=" * 100)
        lines.append("Azure VM Cost Estimate")
        lines.append("=" * 100)

        # Date range if specified
        if summary.date_range and summary.date_range[0]:
            from_date, to_date = summary.date_range
            from_str = from_date.strftime("%Y-%m-%d") if from_date else "VM creation"
            to_str = to_date.strftime("%Y-%m-%d") if to_date else "Now"
            lines.append(f"Period: {from_str} to {to_str}")
            lines.append("-" * 100)

        # Summary statistics
        lines.append(f"Total VMs:        {summary.total_vms}")
        lines.append(f"Running VMs:      {summary.running_vms}")
        lines.append(f"Stopped VMs:      {summary.stopped_vms}")
        lines.append(f"Total Cost:       ${summary.total_cost:.2f}")

        # Monthly estimate for running VMs
        if summary.running_vms > 0:
            monthly = summary.get_monthly_estimate()
            lines.append(f"Monthly Estimate: ${monthly:.2f} (for currently running VMs)")

        # Per-VM breakdown if requested
        if by_vm and summary.estimates:
            lines.append("")
            lines.append("=" * 100)
            lines.append("Per-VM Breakdown")
            lines.append("=" * 100)
            lines.append(f"{'VM NAME':<35} {'SIZE':<18} {'STATUS':<12} {'RATE/HR':<10} {'HOURS':<10} {'COST':<10}")
            lines.append("-" * 100)

            # Sort by cost (highest first)
            sorted_estimates = sorted(
                summary.estimates,
                key=lambda x: x.estimated_cost,
                reverse=True
            )

            for estimate in sorted_estimates:
                status = "Running" if estimate.is_running() else "Stopped"
                lines.append(
                    f"{estimate.vm_name:<35} "
                    f"{estimate.vm_size:<18} "
                    f"{status:<12} "
                    f"${estimate.hourly_rate:<9.4f} "
                    f"{float(estimate.hours_running):<10.1f} "
                    f"${float(estimate.estimated_cost):<9.2f}"
                )

        lines.append("=" * 100)
        lines.append("")
        lines.append("Note: Costs are estimates based on Azure pay-as-you-go pricing.")
        lines.append("For exact costs, check Azure Cost Management in the portal.")
        lines.append("")

        return "\n".join(lines)


__all__ = ['CostTracker', 'CostSummary', 'VMCostEstimate', 'CostTrackerError']
