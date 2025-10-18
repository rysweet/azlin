"""Azure VM Status Dashboard.

This module provides functionality to display VM status information
including resource usage, costs, and configuration details.
"""

import json
import subprocess
from dataclasses import dataclass
from typing import Any

from rich.console import Console
from rich.table import Table


@dataclass
class VMStatus:
    """VM status information."""

    name: str
    status: str
    power_state: str
    resource_group: str
    location: str
    size: str
    public_ip: str | None
    provisioning_state: str
    os_type: str
    uptime: str | None = None
    cpu_usage: float | None = None
    memory_usage: float | None = None
    estimated_cost: float | None = None


class StatusDashboard:
    """Manages VM status display and retrieval."""

    # Approximate hourly costs for common VM sizes (USD)
    VM_COST_ESTIMATES = {
        "Standard_B1s": 0.0104,
        "Standard_B1ms": 0.0207,
        "Standard_B2s": 0.0416,
        "Standard_B2ms": 0.0832,
        "Standard_B4ms": 0.166,
        "Standard_D2s_v3": 0.096,
        "Standard_D4s_v3": 0.192,
        "Standard_D8s_v3": 0.384,
        "Standard_D16s_v3": 0.768,
        "Standard_E2s_v3": 0.126,
        "Standard_E4s_v3": 0.252,
        "Standard_E8s_v3": 0.504,
        "Standard_F2s_v2": 0.085,
        "Standard_F4s_v2": 0.169,
        "Standard_F8s_v2": 0.338,
    }

    def __init__(self):
        """Initialize the status dashboard."""
        self.console = Console()

    def _run_az_command(self, command: list[str]) -> dict[str, Any]:
        """Run an Azure CLI command and return JSON output.

        Args:
            command: Azure CLI command as list of strings

        Returns:
            Parsed JSON output from the command

        Raises:
            subprocess.CalledProcessError: If the command fails
            json.JSONDecodeError: If output is not valid JSON
        """
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            check=True,
        )
        return json.loads(result.stdout) if result.stdout.strip() else {}

    def _get_vm_list(self, resource_group: str | None = None) -> list[dict[str, Any]]:
        """Get list of VMs.

        Args:
            resource_group: Optional resource group filter

        Returns:
            List of VM dictionaries from Azure CLI
        """
        command = ["az", "vm", "list", "--output", "json"]
        if resource_group:
            command.extend(["--resource-group", resource_group])

        return self._run_az_command(command)

    def _get_vm_instance_view(self, vm_name: str, resource_group: str) -> dict[str, Any]:
        """Get detailed instance view for a VM.

        Args:
            vm_name: Name of the VM
            resource_group: Resource group containing the VM

        Returns:
            Instance view dictionary from Azure CLI
        """
        command = [
            "az",
            "vm",
            "get-instance-view",
            "--name",
            vm_name,
            "--resource-group",
            resource_group,
            "--output",
            "json",
        ]
        return self._run_az_command(command)

    def _get_public_ip(self, vm_name: str, resource_group: str) -> str | None:
        """Get public IP address for a VM.

        Args:
            vm_name: Name of the VM
            resource_group: Resource group containing the VM

        Returns:
            Public IP address or None if not found
        """
        try:
            command = [
                "az",
                "vm",
                "list-ip-addresses",
                "--name",
                vm_name,
                "--resource-group",
                resource_group,
                "--output",
                "json",
            ]
            result = self._run_az_command(command)

            if result and len(result) > 0:
                virtual_machine = result[0]
                network_interfaces = (
                    virtual_machine.get("virtualMachine", {})
                    .get("network", {})
                    .get("publicIpAddresses", [])
                )

                if network_interfaces:
                    return network_interfaces[0].get("ipAddress")

            return None
        except (subprocess.CalledProcessError, json.JSONDecodeError, KeyError):
            return None

    def _extract_power_state(self, instance_view: dict[str, Any]) -> str:
        """Extract power state from instance view.

        Args:
            instance_view: Instance view dictionary

        Returns:
            Power state string (e.g., 'Running', 'Stopped', 'Deallocated')
        """
        statuses = instance_view.get("instanceView", {}).get("statuses", [])

        for status in statuses:
            code = status.get("code", "")
            if code.startswith("PowerState/"):
                return code.replace("PowerState/", "")

        return "Unknown"

    def _calculate_uptime(self, instance_view: dict[str, Any]) -> str | None:
        """Calculate VM uptime based on instance view.

        Args:
            instance_view: Instance view dictionary

        Returns:
            Human-readable uptime string or None
        """
        # Azure doesn't directly provide uptime, so we return None for now
        # In a production system, you could track start times separately
        return None

    def _get_estimated_cost(self, vm_size: str, hours: float = 730.0) -> float:
        """Get estimated monthly cost for a VM.

        Args:
            vm_size: Azure VM size (e.g., 'Standard_B1s')
            hours: Hours to calculate for (default 730 = 1 month)

        Returns:
            Estimated cost in USD
        """
        hourly_rate = self.VM_COST_ESTIMATES.get(vm_size, 0.0)
        return hourly_rate * hours

    def get_vm_status(
        self, vm_name: str | None = None, resource_group: str | None = None
    ) -> list[VMStatus]:
        """Get status information for VMs.

        Args:
            vm_name: Optional specific VM name
            resource_group: Optional resource group filter

        Returns:
            List of VMStatus objects
        """
        vm_statuses = []

        # Get VM list
        vms = self._get_vm_list(resource_group)

        # Filter by name if specified
        if vm_name:
            vms = [vm for vm in vms if vm.get("name") == vm_name]

        for vm in vms:
            name = vm.get("name", "Unknown")
            rg = vm.get("resourceGroup", "Unknown")
            location = vm.get("location", "Unknown")
            size = vm.get("hardwareProfile", {}).get("vmSize", "Unknown")
            os_type = vm.get("storageProfile", {}).get("osDisk", {}).get("osType", "Unknown")

            # Get instance view for detailed status
            try:
                instance_view = self._get_vm_instance_view(name, rg)
                power_state = self._extract_power_state(instance_view)
                provisioning_state = instance_view.get("provisioningState", "Unknown")
                uptime = self._calculate_uptime(instance_view)
            except (subprocess.CalledProcessError, json.JSONDecodeError):
                power_state = "Unknown"
                provisioning_state = "Unknown"
                uptime = None

            # Get public IP
            public_ip = self._get_public_ip(name, rg)

            # Calculate estimated cost
            estimated_cost = self._get_estimated_cost(size)

            vm_status = VMStatus(
                name=name,
                status=provisioning_state,
                power_state=power_state,
                resource_group=rg,
                location=location,
                size=size,
                public_ip=public_ip,
                provisioning_state=provisioning_state,
                os_type=os_type,
                uptime=uptime,
                estimated_cost=estimated_cost,
            )

            vm_statuses.append(vm_status)

        return vm_statuses

    def display_status(
        self,
        vm_name: str | None = None,
        resource_group: str | None = None,
        detailed: bool = False,
    ) -> None:
        """Display VM status in a formatted table.

        Args:
            vm_name: Optional specific VM name
            resource_group: Optional resource group filter
            detailed: Whether to show detailed metrics
        """
        vm_statuses = self.get_vm_status(vm_name, resource_group)

        if not vm_statuses:
            self.console.print("[yellow]No VMs found matching the criteria.[/yellow]")
            return

        # Create table
        table = Table(title="Azure VM Status Dashboard", show_header=True)

        # Add columns
        table.add_column("VM Name", style="cyan", no_wrap=True)
        table.add_column("Status", style="green")
        table.add_column("Power State", style="yellow")
        table.add_column("Public IP", style="blue")
        table.add_column("Resource Group", style="magenta")
        table.add_column("Location", style="white")
        table.add_column("Size", style="white")

        if detailed:
            table.add_column("OS Type", style="white")
            table.add_column("Est. Cost/Month", style="red")
            if any(vm.uptime for vm in vm_statuses):
                table.add_column("Uptime", style="white")

        # Add rows
        for vm in vm_statuses:
            # Color code power state
            power_state = vm.power_state
            if power_state == "running":
                power_state_colored = f"[green]{power_state}[/green]"
            elif power_state == "stopped" or power_state == "deallocated":
                power_state_colored = f"[red]{power_state}[/red]"
            else:
                power_state_colored = f"[yellow]{power_state}[/yellow]"

            row = [
                vm.name,
                vm.status,
                power_state_colored,
                vm.public_ip or "N/A",
                vm.resource_group,
                vm.location,
                vm.size,
            ]

            if detailed:
                row.append(vm.os_type)
                row.append(f"${vm.estimated_cost:.2f}" if vm.estimated_cost else "N/A")
                if any(vm.uptime for vm in vm_statuses):
                    row.append(vm.uptime or "N/A")

            table.add_row(*row)

        # Display table
        self.console.print(table)

        # Calculate and display total cost
        if detailed:
            total_cost = sum(
                vm.estimated_cost
                for vm in vm_statuses
                if vm.estimated_cost and vm.power_state == "running"
            )
            self.console.print(
                f"\n[bold]Total Estimated Monthly Cost (Running VMs): [red]${total_cost:.2f}[/red][/bold]"
            )


def show_vm_status(
    vm_name: str | None = None,
    resource_group: str | None = None,
    detailed: bool = False,
) -> None:
    """Show VM status dashboard.

    Args:
        vm_name: Optional specific VM name
        resource_group: Optional resource group filter
        detailed: Whether to show detailed metrics
    """
    dashboard = StatusDashboard()
    dashboard.display_status(vm_name, resource_group, detailed)
