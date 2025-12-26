"""
DHCP Configuration Helper
Generates recommended DHCP configurations for various DHCP servers
"""

from typing import Dict, List, Optional
from dataclasses import dataclass
import socket
import struct


@dataclass
class DHCPConfig:
    """DHCP configuration parameters"""
    pxe_server_ip: str
    http_port: int = 9021
    tftp_port: int = 69
    server_type: str = "dnsmasq"


class DHCPConfigGenerator:
    """Generate DHCP server configurations for PXE boot"""

    def __init__(self):
        self.templates = {
            "dnsmasq": self._generate_dnsmasq,
            "isc-dhcp": self._generate_isc_dhcp,
            "mikrotik": self._generate_mikrotik,
            "windows": self._generate_windows,
        }

    def generate(self, config: DHCPConfig) -> Dict[str, str]:
        """Generate configuration for specified server type"""
        generator = self.templates.get(config.server_type)
        if not generator:
            raise ValueError(f"Unknown server type: {config.server_type}")

        return {
            "type": config.server_type,
            "config": generator(config),
            "description": self._get_description(config.server_type),
            "filename": self._get_filename(config.server_type),
        }

    def _generate_dnsmasq(self, config: DHCPConfig) -> str:
        """Generate dnsmasq configuration"""
        return f"""# iPXE PXE Boot Configuration for dnsmasq
# Add this to /etc/dnsmasq.conf

# Enable TFTP server (if using dnsmasq as TFTP)
enable-tftp
tftp-root=/srv/tftp

# Detect iPXE clients (option 175)
dhcp-match=set:ipxe,175

# Detect architecture types
dhcp-match=set:efi-x86_64,option:client-arch,7
dhcp-match=set:efi-x86_64,option:client-arch,9
dhcp-match=set:bios,option:client-arch,0

# UEFI boot (iPXE already loaded)
dhcp-boot=tag:efi-x86_64,tag:ipxe,http://{config.pxe_server_ip}:{config.http_port}/ipxe/boot.ipxe

# UEFI boot (load iPXE first)
dhcp-boot=tag:efi-x86_64,tag:!ipxe,ipxe.efi,{config.pxe_server_ip}

# Legacy BIOS boot (iPXE already loaded)
dhcp-boot=tag:bios,tag:ipxe,http://{config.pxe_server_ip}:{config.http_port}/ipxe/boot.ipxe

# Legacy BIOS boot (load iPXE first)
dhcp-boot=tag:bios,tag:!ipxe,undionly.kpxe,{config.pxe_server_ip}

# Alternative simple configuration (if tagging doesn't work):
# dhcp-option=66,{config.pxe_server_ip}
# dhcp-option=67,undionly.kpxe

# After editing, reload dnsmasq:
# sudo systemctl reload dnsmasq
"""

    def _generate_isc_dhcp(self, config: DHCPConfig) -> str:
        """Generate ISC DHCP server configuration"""
        return f"""# iPXE PXE Boot Configuration for ISC DHCP Server
# Add this to /etc/dhcp/dhcpd.conf

# Declare iPXE option space
option space ipxe;
option ipxe-encap-opts code 175 = encapsulate ipxe;

# PXE Boot configuration
next-server {config.pxe_server_ip};

# Detect client architecture
if exists user-class and option user-class = "iPXE" {{
    # iPXE already loaded, chain to boot script
    filename "http://{config.pxe_server_ip}:{config.http_port}/ipxe/boot.ipxe";
}} elsif option arch = 00:07 or option arch = 00:09 {{
    # UEFI x64 - load iPXE EFI
    filename "ipxe.efi";
}} else {{
    # Legacy BIOS - load iPXE
    filename "undionly.kpxe";
}}

# After editing, restart dhcpd:
# sudo systemctl restart isc-dhcp-server
"""

    def _generate_mikrotik(self, config: DHCPConfig) -> str:
        """Generate MikroTik RouterOS configuration"""
        return f"""# iPXE PXE Boot Configuration for MikroTik RouterOS
# Run these commands in RouterOS terminal:

# Set TFTP server address
/ip dhcp-server option add name=next-server code=66 value="s'{config.pxe_server_ip}'"

# Set boot filename for BIOS
/ip dhcp-server option add name=bootfile-bios code=67 value="s'undionly.kpxe'"

# Set boot filename for UEFI
/ip dhcp-server option add name=bootfile-uefi code=67 value="s'ipxe.efi'"

# Add options to DHCP server
/ip dhcp-server option sets add name=pxe-options options=next-server,bootfile-bios

# Apply to DHCP server (replace 'dhcp1' with your DHCP server name)
/ip dhcp-server set dhcp1 dhcp-option-set=pxe-options

# Note: MikroTik doesn't natively support iPXE detection (option 175)
# You may need to use DHCP Option Matching for advanced scenarios
"""

    def _generate_windows(self, config: DHCPConfig) -> str:
        """Generate Windows DHCP Server configuration"""
        return f"""# iPXE PXE Boot Configuration for Windows DHCP Server
# Configure via GUI or PowerShell:

## Via GUI (Server Manager):
1. Open DHCP Manager
2. Right-click on IPv4 → Set Predefined Options
3. Add Option 66 (TFTP Server):
   - Name: Boot Server Host Name
   - Data type: String
   - Code: 66
   - Value: {config.pxe_server_ip}

4. Add Option 67 (Bootfile Name):
   - Name: Bootfile Name
   - Data type: String
   - Code: 67
   - Value: undionly.kpxe (for BIOS) or ipxe.efi (for UEFI)

5. Right-click Scope Options → Configure Options
6. Enable Options 66 and 67
7. Set values as above

## Via PowerShell:
# Set Option 66 (TFTP Server)
Set-DhcpServerv4OptionValue -OptionId 66 -Value "{config.pxe_server_ip}"

# Set Option 67 (Boot filename for BIOS)
Set-DhcpServerv4OptionValue -OptionId 67 -Value "undionly.kpxe"

# For UEFI support, you need to create vendor classes
# This is more complex - refer to Microsoft documentation
"""

    def _get_description(self, server_type: str) -> str:
        """Get description for server type"""
        descriptions = {
            "dnsmasq": "Lightweight DNS/DHCP server, common on Linux routers",
            "isc-dhcp": "ISC DHCP Server (dhcpd), traditional Linux DHCP server",
            "mikrotik": "MikroTik RouterOS DHCP server configuration",
            "windows": "Microsoft Windows DHCP Server configuration",
        }
        return descriptions.get(server_type, "")

    def _get_filename(self, server_type: str) -> str:
        """Get config filename for server type"""
        filenames = {
            "dnsmasq": "dnsmasq.conf",
            "isc-dhcp": "dhcpd.conf",
            "mikrotik": "mikrotik-commands.txt",
            "windows": "windows-dhcp-setup.txt",
        }
        return filenames.get(server_type, "config.txt")

    def list_server_types(self) -> List[Dict[str, str]]:
        """List all supported server types"""
        return [
            {"id": "dnsmasq", "name": "dnsmasq", "description": self._get_description("dnsmasq")},
            {"id": "isc-dhcp", "name": "ISC DHCP Server", "description": self._get_description("isc-dhcp")},
            {"id": "mikrotik", "name": "MikroTik RouterOS", "description": self._get_description("mikrotik")},
            {"id": "windows", "name": "Windows DHCP Server", "description": self._get_description("windows")},
        ]


class DHCPValidator:
    """Validate DHCP configuration on the network"""

    def __init__(self):
        pass

    def check_network(self, interface: Optional[str] = None) -> Dict[str, any]:
        """
        Check DHCP configuration on the network
        This is a placeholder - actual implementation would require scapy or similar
        and elevated privileges
        """
        # For now, return a mock response
        # Real implementation would:
        # 1. Send DHCP DISCOVER
        # 2. Receive DHCP OFFER
        # 3. Parse options 66, 67, 175
        # 4. Validate against expected values

        return {
            "status": "not_implemented",
            "message": "Network DHCP validation requires elevated privileges and scapy library",
            "suggestions": [
                "Install scapy: pip install scapy",
                "Run container with NET_ADMIN capability",
                "Or manually verify DHCP settings on your router"
            ]
        }

    def validate_config(self, detected_options: Dict[str, str], expected_server_ip: str) -> Dict[str, any]:
        """Validate detected DHCP options against expected values"""
        issues = []
        warnings = []

        # Check option 66 (Next Server)
        if "option_66" in detected_options:
            if detected_options["option_66"] != expected_server_ip:
                issues.append(f"Option 66 (Next Server) is {detected_options['option_66']}, expected {expected_server_ip}")
        else:
            issues.append("Option 66 (Next Server) not found in DHCP response")

        # Check option 67 (Boot Filename)
        if "option_67" in detected_options:
            valid_bootfiles = ["undionly.kpxe", "ipxe.efi", "ipxe.pxe"]
            if detected_options["option_67"] not in valid_bootfiles:
                warnings.append(f"Option 67 (Boot Filename) is {detected_options['option_67']}, expected one of {valid_bootfiles}")
        else:
            issues.append("Option 67 (Boot Filename) not found in DHCP response")

        # Check option 175 (iPXE detection)
        if "option_175" not in detected_options:
            warnings.append("Option 175 (iPXE detection) not configured - advanced iPXE features may not work")

        return {
            "valid": len(issues) == 0,
            "issues": issues,
            "warnings": warnings
        }
