"""
DHCP configuration management for PXE Boot Station
Handles DHCP server configuration generation and validation
REFACTORED: Using common utilities to eliminate repetition
"""

import ipaddress
from dataclasses import dataclass
from typing import List, Optional, Tuple

# Import common utilities to eliminate repetition
from .utils import safe_operation, safe_write_file, validate_ip_address, validate_string_field


@dataclass
class DHCPConfig:
    """DHCP configuration data structure"""

    server_ip: str
    subnet: str
    netmask: str
    router_ip: str
    dns_servers: List[str]
    lease_time: int = 86400  # 24 hours
    max_lease_time: int = 172800  # 48 hours
    tftp_server: Optional[str] = None
    boot_filename: str = "undionly.kpxe"
    domain_name: Optional[str] = None

    def __post_init__(self):
        """Set TFTP server to server IP if not specified"""
        if self.tftp_server is None:
            self.tftp_server = self.server_ip


class DHCPConfigValidator:
    """DHCP configuration validation utilities"""

    @staticmethod
    def validate_subnet(subnet: str, netmask: str) -> Tuple[bool, str]:
        """Validate subnet and netmask combination"""
        try:
            network = ipaddress.IPv4Network(f"{subnet}/{netmask}", strict=False)
            return True, f"Valid subnet: {network}"
        except (ipaddress.AddressValueError, ipaddress.NetmaskValueError) as e:
            return False, f"Invalid subnet/netmask: {str(e)}"

    @staticmethod
    def validate_ip_in_subnet(ip: str, subnet: str, netmask: str) -> Tuple[bool, str]:
        """Check if IP address is within subnet"""
        try:
            network = ipaddress.IPv4Network(f"{subnet}/{netmask}", strict=False)
            address = ipaddress.IPv4Address(ip)

            if address in network:
                return True, f"IP {ip} is in subnet {network}"
            else:
                return False, f"IP {ip} is NOT in subnet {network}"
        except Exception as e:
            return False, f"Validation error: {str(e)}"

    @staticmethod
    def validate_dns_servers(dns_list: List[str]) -> Tuple[bool, str]:
        """Validate DNS server list using common utility"""
        if not dns_list:
            return False, "DNS server list is empty"

        invalid_dns = []
        for dns in dns_list:
            # Use common validation utility
            is_valid, _ = validate_ip_address(dns)
            if not is_valid:
                invalid_dns.append(dns)

        if invalid_dns:
            return False, f"Invalid DNS servers: {', '.join(invalid_dns)}"

        return True, f"Valid DNS servers: {', '.join(dns_list)}"

    @staticmethod
    def validate_lease_times(lease_time: int, max_lease_time: int) -> Tuple[bool, str]:
        """Validate lease time settings"""
        if lease_time <= 0:
            return False, "Lease time must be positive"

        if max_lease_time <= 0:
            return False, "Max lease time must be positive"

        if lease_time > max_lease_time:
            return False, "Lease time cannot be greater than max lease time"

        return True, f"Valid lease times: {lease_time}s / {max_lease_time}s"

    @classmethod
    @safe_operation("DHCP configuration validation", return_tuple=True)
    def validate_config(cls, config: DHCPConfig) -> Tuple[bool, List[str]]:
        """Validate complete DHCP configuration"""
        errors = []

        # Validate server IP using common utility
        is_valid, msg = validate_ip_address(config.server_ip)
        if not is_valid:
            errors.append(f"Server IP: {msg}")

        # Validate router IP using common utility
        is_valid, msg = validate_ip_address(config.router_ip)
        if not is_valid:
            errors.append(f"Router IP: {msg}")

        # Validate subnet and netmask
        is_valid, msg = cls.validate_subnet(config.subnet, config.netmask)
        if not is_valid:
            errors.append(f"Subnet: {msg}")
        else:
            # Check if server and router are in subnet
            for ip, name in [(config.server_ip, "Server"), (config.router_ip, "Router")]:
                is_valid, msg = cls.validate_ip_in_subnet(ip, config.subnet, config.netmask)
                if not is_valid:
                    errors.append(f"{name}: {msg}")

        # Validate DNS servers using common utility
        is_valid, msg = cls.validate_dns_servers(config.dns_servers)
        if not is_valid:
            errors.append(f"DNS: {msg}")

        # Validate TFTP server using common utility
        if config.tftp_server:
            is_valid, msg = validate_ip_address(config.tftp_server)
            if not is_valid:
                errors.append(f"TFTP Server: {msg}")

        # Validate lease times
        is_valid, msg = cls.validate_lease_times(config.lease_time, config.max_lease_time)
        if not is_valid:
            errors.append(f"Lease times: {msg}")

        # Validate domain name if provided using common utility
        if config.domain_name:
            is_valid, msg = validate_string_field(
                config.domain_name,
                field_name="Domain name",
                min_length=3,
                max_length=253,
                allowed_chars=r"^[a-zA-Z0-9.-]+$",
            )
            if not is_valid:
                errors.append(f"Domain name: {msg}")

        # Validate boot filename using common utility
        is_valid, msg = validate_string_field(
            config.boot_filename, field_name="Boot filename", min_length=1, max_length=128
        )
        if not is_valid:
            errors.append(f"Boot filename: {msg}")

        return len(errors) == 0, errors


class DHCPConfigGenerator:
    """DHCP configuration file generators"""

    @staticmethod
    @safe_operation("ISC DHCP configuration generation")
    def generate_isc_dhcp_config(config: DHCPConfig) -> str:
        """Generate ISC DHCP server configuration"""
        template = f"""# ISC DHCP Server Configuration
# Generated by PXE Boot Station

# Global settings
default-lease-time {config.lease_time};
max-lease-time {config.max_lease_time};
authoritative;

# PXE Boot settings
option space pxelinux;
option pxelinux.magic code 208 = string;
option pxelinux.configfile code 209 = text;
option pxelinux.pathprefix code 210 = text;
option pxelinux.reboottime code 211 = unsigned integer 32;
vendor-option-space pxelinux;

# Subnet configuration
subnet {config.subnet} netmask {config.netmask} {{
    # Network settings
    option routers {config.router_ip};
    option domain-name-servers {', '.join(config.dns_servers)};"""

        if config.domain_name:
            template += f"""
    option domain-name "{config.domain_name}";"""

        template += f"""

    # PXE Boot settings
    option tftp-server-name "{config.tftp_server}";
    option bootfile-name "{config.boot_filename}";

    # DHCP range (adjust as needed)
    range {_calculate_dhcp_range(config.subnet, config.netmask)};
}}

# Host-specific configurations (add as needed)
# host pxe-client {{
#     hardware ethernet 00:11:22:33:44:55;
#     fixed-address 192.168.1.100;
# }}
"""
        return template

    @staticmethod
    @safe_operation("dnsmasq configuration generation")
    def generate_dnsmasq_config(config: DHCPConfig) -> str:
        """Generate dnsmasq DHCP configuration"""
        dns_servers = ",".join(config.dns_servers)
        dhcp_range_start, dhcp_range_end = _calculate_dhcp_range(
            config.subnet, config.netmask
        ).split(" ")

        template = f"""# dnsmasq DHCP Configuration
# Generated by PXE Boot Station

# Interface to listen on (adjust as needed)
interface=eth0

# DHCP range and lease time
dhcp-range={dhcp_range_start},{dhcp_range_end},{config.netmask},{config.lease_time}s

# Gateway and DNS
dhcp-option=3,{config.router_ip}
dhcp-option=6,{dns_servers}"""

        if config.domain_name:
            template += f"""
dhcp-option=15,{config.domain_name}"""

        template += f"""

# PXE Boot settings
dhcp-boot={config.boot_filename},{config.tftp_server}

# Enable TFTP server
enable-tftp
tftp-root=/srv/tftp

# Logging
log-dhcp
log-queries
"""
        return template

    @staticmethod
    @safe_operation("MikroTik configuration generation")
    def generate_mikrotik_config(config: DHCPConfig) -> str:
        """Generate MikroTik DHCP configuration commands"""
        dhcp_range_start, dhcp_range_end = _calculate_dhcp_range(
            config.subnet, config.netmask
        ).split(" ")
        dns_servers = ",".join(config.dns_servers)

        commands = f"""# MikroTik DHCP Configuration
# Generated by PXE Boot Station
# Copy and paste these commands into MikroTik terminal

# Create DHCP pool
/ip pool add name=dhcp-pool ranges={dhcp_range_start}-{dhcp_range_end}

# Configure DHCP server network
/ip dhcp-server network add address={config.subnet}/{_netmask_to_cidr(config.netmask)} \\
    gateway={config.router_ip} dns-server={dns_servers}"""

        if config.domain_name:
            commands += f" domain={config.domain_name}"

        commands += f"""

# Create DHCP server
/ip dhcp-server add interface=bridge pool=dhcp-pool lease-time={_seconds_to_time(config.lease_time)} \\
    disabled=no

# Configure PXE boot options
/ip dhcp-server option add name=tftp-server code=66 value="'{config.tftp_server}'"
/ip dhcp-server option add name=boot-filename code=67 value="'{config.boot_filename}'"

# Apply options to DHCP server
/ip dhcp-server network set [find address="{config.subnet}/{_netmask_to_cidr(config.netmask)}"] \\
    dhcp-option=tftp-server,boot-filename
"""
        return commands


class DHCPConfigManager:
    """Main DHCP configuration management class"""

    def __init__(self):
        self.validator = DHCPConfigValidator()
        self.generator = DHCPConfigGenerator()

    @safe_operation("DHCP configuration creation")
    def create_config(
        self,
        server_ip: str,
        subnet: str,
        netmask: str,
        router_ip: str,
        dns_servers: List[str],
        **kwargs,
    ) -> DHCPConfig:
        """Create DHCP configuration object"""
        return DHCPConfig(
            server_ip=server_ip,
            subnet=subnet,
            netmask=netmask,
            router_ip=router_ip,
            dns_servers=dns_servers,
            **kwargs,
        )

    @safe_operation("DHCP configuration validation and generation", return_tuple=True)
    def validate_and_generate(
        self, config: DHCPConfig, config_type: str = "isc"
    ) -> Tuple[bool, str, str]:
        """Validate configuration and generate config file"""
        # Validate configuration
        is_valid, errors = self.validator.validate_config(config)

        if not is_valid:
            error_msg = "Configuration validation failed:\n" + "\n".join(
                f"• {error}" for error in errors
            )
            return False, error_msg, ""

        # Generate configuration
        if config_type.lower() == "isc":
            config_content = self.generator.generate_isc_dhcp_config(config)
        elif config_type.lower() == "dnsmasq":
            config_content = self.generator.generate_dnsmasq_config(config)
        elif config_type.lower() == "mikrotik":
            config_content = self.generator.generate_mikrotik_config(config)
        else:
            return False, f"Unsupported configuration type: {config_type}", ""

        success_msg = f"✅ {config_type.upper()} configuration generated successfully"
        return True, success_msg, config_content

    def save_config(self, config_content: str, filepath: str) -> Tuple[bool, str]:
        """Save configuration to file using common utility"""
        if not config_content.strip():
            return False, "❌ No configuration content to save"

        # Use common utility for safe file writing
        return safe_write_file(filepath, config_content)


# Helper functions
def _calculate_dhcp_range(subnet: str, netmask: str) -> str:
    """Calculate DHCP range from subnet and netmask"""
    try:
        network = ipaddress.IPv4Network(f"{subnet}/{netmask}", strict=False)
        # Use middle 50% of the network for DHCP range
        hosts = list(network.hosts())
        if len(hosts) < 4:
            # Very small network, use all available hosts except first and last
            start_ip = str(hosts[0])
            end_ip = str(hosts[-1])
        else:
            # Skip first 25% and last 25% of addresses
            start_idx = len(hosts) // 4
            end_idx = len(hosts) - (len(hosts) // 4)
            start_ip = str(hosts[start_idx])
            end_ip = str(hosts[end_idx - 1])

        return f"{start_ip} {end_ip}"
    except Exception:
        return "192.168.1.100 192.168.1.200"  # Fallback range


def _netmask_to_cidr(netmask: str) -> int:
    """Convert netmask to CIDR notation"""
    try:
        return ipaddress.IPv4Network(f"0.0.0.0/{netmask}").prefixlen
    except Exception:
        return 24  # Default /24


def _seconds_to_time(seconds: int) -> str:
    """Convert seconds to time format for MikroTik"""
    if seconds >= 86400:  # days
        days = seconds // 86400
        return f"{days}d"
    elif seconds >= 3600:  # hours
        hours = seconds // 3600
        return f"{hours}h"
    elif seconds >= 60:  # minutes
        minutes = seconds // 60
        return f"{minutes}m"
    else:
        return f"{seconds}s"


# Convenience functions for common network configurations
@safe_operation("Simple DHCP configuration creation")
def create_simple_config(
    server_ip: str, network_cidr: str, dns_servers: Optional[List[str]] = None
) -> DHCPConfig:
    """Create simple DHCP configuration from network CIDR"""
    network = ipaddress.IPv4Network(network_cidr, strict=False)
    subnet = str(network.network_address)
    netmask = str(network.netmask)

    # Assume server is also the router
    router_ip = server_ip

    # Default DNS servers if not provided
    if dns_servers is None:
        dns_servers = ["8.8.8.8", "8.8.4.4"]

    return DHCPConfig(
        server_ip=server_ip,
        subnet=subnet,
        netmask=netmask,
        router_ip=router_ip,
        dns_servers=dns_servers,
    )
