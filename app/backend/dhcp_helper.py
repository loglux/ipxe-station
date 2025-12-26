"""
DHCP Configuration Helper
Generates recommended DHCP configurations for various DHCP servers
"""

from typing import Dict, List, Optional, Any
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
        self.timeout = 5  # seconds

    def check_network(self, interface: Optional[str] = None, expected_server_ip: str = "192.168.10.32") -> Dict[str, Any]:
        """
        Check DHCP configuration on the network using DHCP DISCOVER/OFFER
        """
        try:
            from scapy.all import conf, get_if_hwaddr, get_if_addr, Ether, IP, UDP, BOOTP, DHCP, srp1
            import random

            # Use default interface if not specified
            if interface is None:
                interface = conf.iface

            # Convert interface to string if it's a scapy NetworkInterface object
            interface_name = str(interface) if interface else "unknown"

            # Get interface MAC and IP
            try:
                mac_addr = get_if_hwaddr(interface_name)
                ip_addr = get_if_addr(interface_name)
            except Exception as e:
                return {
                    "status": "error",
                    "message": f"Failed to get interface info: {e}",
                    "interface": interface_name,
                    "suggestions": [
                        "Check if the interface exists",
                        "Ensure the container has NET_ADMIN capability",
                        "Try specifying a different interface"
                    ]
                }

            # Generate random transaction ID
            xid = random.randint(1, 900000000)

            # Create DHCP DISCOVER packet
            discover = (
                Ether(dst="ff:ff:ff:ff:ff:ff", src=mac_addr) /
                IP(src="0.0.0.0", dst="255.255.255.255") /
                UDP(sport=68, dport=67) /
                BOOTP(
                    op=1,  # BOOTREQUEST
                    chaddr=mac_addr,
                    xid=xid,
                    flags=0x8000  # Broadcast flag
                ) /
                DHCP(options=[
                    ("message-type", "discover"),
                    ("client_id", b'\x01' + bytes.fromhex(mac_addr.replace(':', ''))),
                    ("param_req_list", [1, 3, 6, 15, 66, 67, 175]),  # Request options including PXE options
                    "end"
                ])
            )

            # Send DISCOVER and wait for OFFER
            offer = srp1(
                discover,
                iface=interface_name,
                timeout=self.timeout,
                verbose=False
            )

            if offer is None:
                return {
                    "status": "no_response",
                    "message": "No DHCP OFFER received from network",
                    "interface": interface_name,
                    "suggestions": [
                        "Check if DHCP server is running on the network",
                        "Verify network connectivity",
                        "Try increasing timeout or using different interface"
                    ]
                }

            # Parse DHCP options from OFFER
            dhcp_options = {}
            if offer.haslayer(DHCP):
                for option in offer[DHCP].options:
                    if isinstance(option, tuple) and len(option) >= 2:
                        opt_name, opt_value = option[0], option[1]
                        dhcp_options[opt_name] = opt_value

            # Extract PXE-related options
            detected = {
                "dhcp_server": offer[IP].src if offer.haslayer(IP) else "Unknown",
                "offered_ip": offer[BOOTP].yiaddr if offer.haslayer(BOOTP) else "Unknown",
            }

            # Option 66: TFTP server name/IP
            if 66 in dhcp_options or "tftp_server" in dhcp_options:
                tftp_server = dhcp_options.get(66) or dhcp_options.get("tftp_server")
                if isinstance(tftp_server, bytes):
                    tftp_server = tftp_server.decode('utf-8', errors='ignore')
                detected["option_66_tftp_server"] = tftp_server

            # Option 67: Bootfile name
            if 67 in dhcp_options or "bootfile" in dhcp_options:
                bootfile = dhcp_options.get(67) or dhcp_options.get("bootfile")
                if isinstance(bootfile, bytes):
                    bootfile = bootfile.decode('utf-8', errors='ignore')
                detected["option_67_bootfile"] = bootfile

            # Check if PXE options are configured
            issues = []
            warnings = []

            if "option_66_tftp_server" not in detected:
                issues.append("Option 66 (TFTP Server) not configured in DHCP")
            elif detected["option_66_tftp_server"] != expected_server_ip:
                warnings.append(
                    f"Option 66 points to {detected['option_66_tftp_server']}, "
                    f"expected {expected_server_ip}"
                )

            if "option_67_bootfile" not in detected:
                issues.append("Option 67 (Boot Filename) not configured in DHCP")
            else:
                valid_bootfiles = ["undionly.kpxe", "ipxe.efi", "ipxe.pxe"]
                if detected["option_67_bootfile"] not in valid_bootfiles:
                    warnings.append(
                        f"Option 67 is '{detected['option_67_bootfile']}', "
                        f"expected one of {valid_bootfiles}"
                    )

            # Determine overall status
            if len(issues) == 0 and len(warnings) == 0:
                status = "valid"
                message = "DHCP server is correctly configured for PXE boot"
            elif len(issues) > 0:
                status = "invalid"
                message = "DHCP server is missing required PXE boot options"
            else:
                status = "warning"
                message = "DHCP server has PXE boot options but with potential issues"

            return {
                "status": status,
                "message": message,
                "interface": interface_name,
                "detected": detected,
                "issues": issues,
                "warnings": warnings,
                "all_options": {
                    str(k): str(v) if not isinstance(v, (list, tuple)) else [str(x) for x in v]
                    for k, v in dhcp_options.items()
                    if k != "end"
                }
            }

        except ImportError:
            return {
                "status": "error",
                "message": "Scapy library not installed",
                "suggestions": [
                    "Install scapy: pip install scapy",
                    "Rebuild the container with updated requirements.txt"
                ]
            }
        except PermissionError:
            return {
                "status": "error",
                "message": "Insufficient privileges to send/receive network packets",
                "suggestions": [
                    "Run container with NET_ADMIN capability",
                    "Add 'cap_add: [NET_ADMIN]' to docker-compose.yml",
                    "Or run with --privileged flag (not recommended)"
                ]
            }
        except Exception as e:
            return {
                "status": "error",
                "message": f"DHCP validation failed: {str(e)}",
                "error_type": type(e).__name__,
                "suggestions": [
                    "Check network connectivity",
                    "Verify interface name",
                    "Ensure DHCP server is reachable"
                ]
            }

    def validate_config(self, detected_options: Dict[str, str], expected_server_ip: str) -> Dict[str, Any]:
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
