terraform {
  required_version = ">= 1.0"
  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "~> 3.0"
    }
  }
}

provider "azurerm" {
  features {}
}

# Resource Group
resource "azurerm_resource_group" "test" {
  name     = var.resource_group_name
  location = var.location

  tags = {
    purpose     = "azdoit-testing"
    managed_by  = "terraform"
    environment = "test"
  }
}

# Virtual Network
resource "azurerm_virtual_network" "test" {
  name                = "test-azdoit-vnet"
  address_space       = ["10.0.0.0/16"]
  location            = azurerm_resource_group.test.location
  resource_group_name = azurerm_resource_group.test.name

  tags = {
    purpose     = "azdoit-testing"
    managed_by  = "terraform"
    environment = "test"
  }
}

# Subnet
resource "azurerm_subnet" "test" {
  name                 = "test-azdoit-subnet"
  resource_group_name  = azurerm_resource_group.test.name
  virtual_network_name = azurerm_virtual_network.test.name
  address_prefixes     = ["10.0.1.0/24"]
}

# Public IP
resource "azurerm_public_ip" "test" {
  name                = "test-azdoit-vm-1PublicIP"
  location            = azurerm_resource_group.test.location
  resource_group_name = azurerm_resource_group.test.name
  allocation_method   = "Static"
  sku                 = "Standard"

  tags = {
    purpose     = "azdoit-testing"
    managed_by  = "terraform"
    environment = "test"
  }
}

# Network Security Group
resource "azurerm_network_security_group" "test" {
  name                = "test-azdoit-nsg"
  location            = azurerm_resource_group.test.location
  resource_group_name = azurerm_resource_group.test.name

  security_rule {
    name                       = "SSH"
    priority                   = 1001
    direction                  = "Inbound"
    access                     = "Allow"
    protocol                   = "Tcp"
    source_port_range          = "*"
    destination_port_range     = "22"
    source_address_prefix      = "*"
    destination_address_prefix = "*"
  }

  tags = {
    purpose     = "azdoit-testing"
    managed_by  = "terraform"
    environment = "test"
  }
}

# Network Interface
resource "azurerm_network_interface" "test" {
  name                = "test-azdoit-vm-1-nic"
  location            = azurerm_resource_group.test.location
  resource_group_name = azurerm_resource_group.test.name

  ip_configuration {
    name                          = "internal"
    subnet_id                     = azurerm_subnet.test.id
    private_ip_address_allocation = "Dynamic"
    public_ip_address_id          = azurerm_public_ip.test.id
  }

  tags = {
    purpose     = "azdoit-testing"
    managed_by  = "terraform"
    environment = "test"
  }
}

# Associate NSG with Network Interface
resource "azurerm_network_interface_security_group_association" "test" {
  network_interface_id      = azurerm_network_interface.test.id
  network_security_group_id = azurerm_network_security_group.test.id
}

# Linux Virtual Machine
resource "azurerm_linux_virtual_machine" "test" {
  name                = "test-azdoit-vm-1"
  location            = azurerm_resource_group.test.location
  resource_group_name = azurerm_resource_group.test.name
  size                = var.vm_size
  admin_username      = var.admin_username

  network_interface_ids = [
    azurerm_network_interface.test.id,
  ]

  admin_ssh_key {
    username   = var.admin_username
    public_key = var.ssh_public_key
  }

  custom_data = base64encode(file("${path.module}/cloud-init.yml"))

  os_disk {
    name                 = "test-azdoit-vm-1-osdisk"
    caching              = "ReadWrite"
    storage_account_type = "Standard_LRS"
  }

  source_image_reference {
    publisher = "Canonical"
    offer     = "0001-com-ubuntu-server-jammy"
    sku       = "22_04-lts-gen2"
    version   = "latest"
  }

  tags = {
    purpose     = "azdoit-testing"
    managed_by  = "terraform"
    environment = "test"
  }
}
