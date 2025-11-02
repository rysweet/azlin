"""Azure resource cost estimation module.

Provides cost estimation for Azure resources used by azlin including Bastion,
private endpoints, VNet peering, and NFS storage. Prices are based on East US
region as of January 2025.

Example:
    >>> from azlin.modules.cost_estimator import CostEstimator
    >>>
    >>> # Estimate Bastion cost
    >>> bastion_cost = CostEstimator.estimate_bastion_cost("Basic")
    >>> print(CostEstimator.format_cost(bastion_cost))
    $143.65/month
    >>>
    >>> # Estimate private endpoint with data transfer
    >>> pe_cost = CostEstimator.estimate_private_endpoint_cost(100)
    >>> print(CostEstimator.format_cost(pe_cost))
    $8.30/month
    >>>
    >>> # Estimate NFS storage
    >>> nfs_cost = CostEstimator.estimate_nfs_cost(100, "Premium")
    >>> print(CostEstimator.format_cost(nfs_cost))
    $20.00/month
"""


class CostEstimator:
    """Estimate monthly costs for Azure resources.

    All prices are in USD and represent monthly costs unless otherwise noted.
    Pricing is based on East US region as of January 2025.

    Constants:
        BASTION_BASIC: Azure Bastion Basic SKU monthly cost
        BASTION_STANDARD: Azure Bastion Standard SKU monthly cost
        PUBLIC_IP_STATIC: Static public IP address monthly cost
        PRIVATE_ENDPOINT: Private endpoint monthly cost
        VNET_PEERING_GB: VNet peering cost per GB transferred
        NFS_PREMIUM_GB: Azure Files NFS Premium tier cost per GB/month
        NFS_STANDARD_GB: Azure Files NFS Standard tier cost per GB/month
    """

    # Pricing constants (USD/month unless noted)
    # Based on East US region pricing as of January 2025
    BASTION_BASIC = 140.00  # ~$0.19/hour
    BASTION_STANDARD = 289.00  # ~$0.38/hour
    PUBLIC_IP_STATIC = 3.65
    PRIVATE_ENDPOINT = 7.30
    VNET_PEERING_GB = 0.01  # per GB
    NFS_PREMIUM_GB = 0.20  # per GB/month
    NFS_STANDARD_GB = 0.06  # per GB/month

    @staticmethod
    def estimate_bastion_cost(sku: str = "Basic") -> float:
        """Estimate monthly Azure Bastion cost including required public IP.

        Azure Bastion requires a static public IP address in addition to the
        Bastion host itself. This method returns the total monthly cost.

        Args:
            sku: Bastion SKU, either "Basic" or "Standard". Case-insensitive.
                Basic supports basic features for up to 25 concurrent sessions.
                Standard supports advanced features like IP-based connection,
                shareable links, and native client support for up to 100 concurrent sessions.

        Returns:
            Total monthly cost in USD including Bastion host and public IP.

        Raises:
            ValueError: If sku is not "Basic" or "Standard".

        Example:
            >>> cost = CostEstimator.estimate_bastion_cost("Basic")
            >>> assert cost == 143.65  # 140.00 + 3.65
            >>>
            >>> cost = CostEstimator.estimate_bastion_cost("Standard")
            >>> assert cost == 292.65  # 289.00 + 3.65
            >>>
            >>> try:
            ...     CostEstimator.estimate_bastion_cost("Premium")
            ... except ValueError as e:
            ...     assert "Invalid Bastion SKU" in str(e)
        """
        sku_normalized = sku.strip().lower()

        if sku_normalized == "basic":
            bastion_cost = CostEstimator.BASTION_BASIC
        elif sku_normalized == "standard":
            bastion_cost = CostEstimator.BASTION_STANDARD
        else:
            raise ValueError(f"Invalid Bastion SKU: {sku}. Must be 'Basic' or 'Standard'.")

        # Bastion requires a static public IP
        total_cost = bastion_cost + CostEstimator.PUBLIC_IP_STATIC

        return total_cost

    @staticmethod
    def estimate_private_endpoint_cost(expected_data_transfer_gb: float = 100) -> float:
        """Estimate monthly private endpoint cost including VNet peering data transfer.

        Private endpoints enable secure connections to Azure services over a private
        IP address in your VNet. Data transferred over VNet peering incurs additional
        charges.

        Args:
            expected_data_transfer_gb: Expected monthly data transfer in GB over
                VNet peering. Default is 100 GB. Must be non-negative.

        Returns:
            Total monthly cost in USD including private endpoint and data transfer.

        Raises:
            ValueError: If expected_data_transfer_gb is negative.

        Example:
            >>> # Private endpoint with 100 GB transfer
            >>> cost = CostEstimator.estimate_private_endpoint_cost(100)
            >>> assert cost == 8.30  # 7.30 + (100 * 0.01)
            >>>
            >>> # Private endpoint with no data transfer
            >>> cost = CostEstimator.estimate_private_endpoint_cost(0)
            >>> assert cost == 7.30
            >>>
            >>> # Private endpoint with 1 TB transfer
            >>> cost = CostEstimator.estimate_private_endpoint_cost(1024)
            >>> assert cost == 17.54  # 7.30 + (1024 * 0.01)
            >>>
            >>> try:
            ...     CostEstimator.estimate_private_endpoint_cost(-100)
            ... except ValueError as e:
            ...     assert "non-negative" in str(e)
        """
        if expected_data_transfer_gb < 0:
            raise ValueError(
                f"Data transfer must be non-negative, got {expected_data_transfer_gb} GB"
            )

        # Private endpoint base cost
        pe_cost = CostEstimator.PRIVATE_ENDPOINT

        # VNet peering data transfer cost
        transfer_cost = expected_data_transfer_gb * CostEstimator.VNET_PEERING_GB

        total_cost = pe_cost + transfer_cost

        return total_cost

    @staticmethod
    def estimate_nfs_cost(size_gb: int, tier: str = "Premium") -> float:
        """Estimate monthly Azure Files NFS storage cost.

        Azure Files NFS is used for shared home directories and persistent storage.
        Premium tier offers better performance with SSD-backed storage, while
        Standard tier provides cost-effective HDD-backed storage.

        Args:
            size_gb: Storage size in GB. Must be positive. Minimum provisioned
                size for Premium is typically 100 GB in Azure.
            tier: Storage tier, either "Premium" or "Standard". Case-insensitive.
                Premium uses SSD with lower latency and higher throughput.
                Standard uses HDD for cost-effective capacity.

        Returns:
            Total monthly cost in USD based on provisioned size.

        Raises:
            ValueError: If size_gb is not positive or tier is invalid.

        Example:
            >>> # 100 GB Premium NFS
            >>> cost = CostEstimator.estimate_nfs_cost(100, "Premium")
            >>> assert cost == 20.00  # 100 * 0.20
            >>>
            >>> # 500 GB Standard NFS
            >>> cost = CostEstimator.estimate_nfs_cost(500, "Standard")
            >>> assert cost == 30.00  # 500 * 0.06
            >>>
            >>> # 1 TB Premium NFS
            >>> cost = CostEstimator.estimate_nfs_cost(1024, "Premium")
            >>> assert cost == 204.80  # 1024 * 0.20
            >>>
            >>> try:
            ...     CostEstimator.estimate_nfs_cost(0, "Premium")
            ... except ValueError as e:
            ...     assert "positive" in str(e)
            >>>
            >>> try:
            ...     CostEstimator.estimate_nfs_cost(100, "Basic")
            ... except ValueError as e:
            ...     assert "Invalid tier" in str(e)
        """
        if size_gb <= 0:
            raise ValueError(f"Storage size must be positive, got {size_gb} GB")

        tier_normalized = tier.strip().lower()

        if tier_normalized == "premium":
            rate = CostEstimator.NFS_PREMIUM_GB
        elif tier_normalized == "standard":
            rate = CostEstimator.NFS_STANDARD_GB
        else:
            raise ValueError(f"Invalid tier: {tier}. Must be 'Premium' or 'Standard'.")

        total_cost = size_gb * rate

        return total_cost

    @staticmethod
    def format_cost(amount: float) -> str:
        """Format cost for display with currency symbol and time period.

        Args:
            amount: Cost amount in USD.

        Returns:
            Formatted string in the format "$X.XX/month".

        Example:
            >>> formatted = CostEstimator.format_cost(143.65)
            >>> assert formatted == "$143.65/month"
            >>>
            >>> formatted = CostEstimator.format_cost(0)
            >>> assert formatted == "$0.00/month"
            >>>
            >>> formatted = CostEstimator.format_cost(1234.5)
            >>> assert formatted == "$1234.50/month"
            >>>
            >>> # Handles high precision
            >>> formatted = CostEstimator.format_cost(123.456789)
            >>> assert formatted == "$123.46/month"
        """
        return f"${amount:.2f}/month"


# Public interface
__all__ = ["CostEstimator"]
