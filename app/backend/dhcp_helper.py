"""
DHCP Configuration Helper
Generates recommended DHCP configurations for various DHCP servers
"""

from dataclasses import dataclass
from typing import Any, Dict, List, Optional


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
            {
                "id": "isc-dhcp",
                "name": "ISC DHCP Server",
                "description": self._get_description("isc-dhcp"),
            },
            {
                "id": "mikrotik",
                "name": "MikroTik RouterOS",
                "description": self._get_description("mikrotik"),
            },
            {
                "id": "windows",
                "name": "Windows DHCP Server",
                "description": self._get_description("windows"),
            },
        ]


class DHCPValidator:
    """Validate DHCP configuration on the network."""

    def __init__(self):
        self.timeout = 5  # seconds

    def _get_default_iface(self) -> str:
        """Return the interface used for the default route."""
        try:
            with open("/proc/net/route") as f:
                for line in f.readlines()[1:]:
                    fields = line.strip().split()
                    if len(fields) >= 2 and fields[1] == "00000000":
                        return fields[0]
        except OSError:
            pass
        return "eth0"

    def _parse_options(self, data: bytes) -> Dict[int, bytes]:
        """Parse DHCP options from raw packet bytes (starting after BOOTP header)."""
        options: Dict[int, bytes] = {}
        if len(data) < 240 or data[236:240] != b"\x63\x82\x53\x63":
            return options
        i = 240
        while i < len(data):
            opt = data[i]
            if opt == 255:  # END
                break
            if opt == 0:  # PAD
                i += 1
                continue
            if i + 1 >= len(data):
                break
            length = data[i + 1]
            options[opt] = data[i + 2 : i + 2 + length]
            i += 2 + length
        return options

    # Vendor class strings per architecture (sent in option 60)
    _VENDOR_CLASS: Dict[int, bytes] = {
        0: b"PXEClient:Arch:00000:UNDI:002001",  # BIOS x86
        6: b"PXEClient:Arch:00006:UNDI:002001",  # UEFI x86-32
        7: b"PXEClient:Arch:00007:UNDI:003016",  # UEFI x64
        9: b"PXEClient:Arch:00009:UNDI:003016",  # UEFI x64 (alt)
    }

    @staticmethod
    def _ip_checksum(data: bytes) -> int:
        """RFC 1071 one's-complement checksum."""
        import struct

        if len(data) % 2:
            data += b"\x00"
        s = sum(struct.unpack_from("!%dH" % (len(data) // 2), data))
        while s >> 16:
            s = (s & 0xFFFF) + (s >> 16)
        return ~s & 0xFFFF

    def _wrap_ip_udp(self, dhcp_payload: bytes) -> bytes:
        """Wrap a DHCP payload in a IP+UDP datagram with source IP 0.0.0.0.

        Using source 0.0.0.0 makes the router treat our probe as a fresh
        PXE client (no existing DHCP lease) and avoids per-source rate-limiting.
        """
        import random
        import struct

        udp_len = 8 + len(dhcp_payload)
        udp_header = struct.pack("!HHHH", 68, 67, udp_len, 0)  # checksum=0 (optional in IPv4)

        ip_payload = udp_header + dhcp_payload
        ip_id = random.randint(1, 0xFFFF)
        ip_hdr = struct.pack(
            "!BBHHHBBH4s4s",
            0x45,
            0x00,  # Version+IHL, DSCP
            20 + len(ip_payload),  # Total length
            ip_id,  # Identification
            0x4000,  # DF flag, no fragment offset
            64,  # TTL
            17,  # Protocol: UDP
            0,  # Checksum placeholder
            b"\x00\x00\x00\x00",  # Source: 0.0.0.0
            b"\xff\xff\xff\xff",  # Destination: 255.255.255.255
        )
        ck = self._ip_checksum(ip_hdr)
        ip_hdr = ip_hdr[:10] + struct.pack("!H", ck) + ip_hdr[12:]
        return ip_hdr + ip_payload

    def _build_discover(
        self, probe_mac: bytes, xid: int, arch: Optional[int], is_ipxe: bool
    ) -> bytes:
        """Build a DHCP DISCOVER packet for a specific client type.

        When *arch* is None, no PXE options (60, 93, 175) are added — this produces
        a plain DHCP DISCOVER that only a real IP-assignment DHCP server will answer.
        dnsmasq in proxy mode ignores plain (non-PXEClient) DISCOVERs.
        """
        import struct

        pkt = struct.pack("!BBBBIHH", 1, 1, 6, 0, xid, 0, 0x8000)
        pkt += b"\x00" * 4  # ciaddr
        pkt += b"\x00" * 4  # yiaddr
        pkt += b"\x00" * 4  # siaddr
        pkt += b"\x00" * 4  # giaddr
        pkt += probe_mac + b"\x00" * 10  # chaddr (16 bytes)
        pkt += b"\x00" * 64  # sname
        pkt += b"\x00" * 128  # file
        pkt += b"\x63\x82\x53\x63"  # DHCP magic cookie
        pkt += b"\x35\x01\x01"  # option 53: DHCP DISCOVER
        if arch is not None:
            vendor_class = self._VENDOR_CLASS.get(arch, b"PXEClient:Arch:00000:UNDI:002001")
            pkt += b"\x3c" + bytes([len(vendor_class)]) + vendor_class  # option 60: vendor class
            pkt += bytes([0x5D, 0x02, (arch >> 8) & 0xFF, arch & 0xFF])  # option 93: client arch
        if is_ipxe:
            pkt += b"\xaf\x01\x00"  # option 175: iPXE extensions tag
        pkt += b"\x37\x07\x01\x03\x06\x0f\x42\x43\x2b"  # param request list
        pkt += b"\xff"  # END
        return pkt

    @staticmethod
    def _parse_pxe_opt43(data: bytes) -> Dict[str, Any]:
        """Extract PXE boot server IP and boot filename from option 43 sub-options.

        dnsmasq option 43 sub-option layout (observed in proxy mode):
          Sub-opt  6: PXE Discovery Control (1 byte)
          Sub-opt  8: Boot Servers — type(2) count(1) ip(4)*count  ← server IP here
          Sub-opt  9: Boot Menu label — type(2) desc_len(1) desc(n)
          Sub-opt 10: Menu Prompt — timeout(1) text(n)
        The bootfile name is NOT present in DHCP when using pxe-service;
        the client fetches it from the TFTP server via PXE boot negotiation.
        """
        import socket as _socket

        result: Dict[str, Any] = {"server": None}
        i = 0
        while i < len(data):
            code = data[i]
            if code == 0xFF:
                break
            if code == 0x00:
                i += 1
                continue
            if i + 1 >= len(data):
                break
            length = data[i + 1]
            if i + 2 + length > len(data):
                break
            value = data[i + 2 : i + 2 + length]
            if code == 8 and length >= 7:
                # Sub-opt 8: Boot Servers — type(2) count(1) ip(4)*count
                # dnsmasq puts the server IP here; sub-opt 9 is the Boot Menu label
                count = value[2] if len(value) > 2 else 0
                if count >= 1 and len(value) >= 7:
                    result["server"] = _socket.inet_ntoa(value[3:7])
            i += 2 + length
        return result

    def _parse_offer(self, data: bytes, addr: tuple) -> Dict[str, Any]:
        """Extract TFTP server and boot filename from a raw DHCP OFFER.

        Checks (in priority order):
          1. DHCP option 66 / siaddr  — classic TFTP server
          2. DHCP option 67 / BOOTP file field — classic boot filename
          3. Option 43 sub-opt 9 (PXE Boot Server List) — proxy DHCP via pxe-service
        """
        import socket as _socket

        yiaddr = _socket.inet_ntoa(data[16:20])
        siaddr = _socket.inet_ntoa(data[20:24])
        bootp_file = data[108:236].rstrip(b"\x00").decode("utf-8", errors="replace")
        options = self._parse_options(data)

        result: Dict[str, Any] = {
            "dhcp_server": addr[0],
            "offered_ip": yiaddr,
            "tftp_server": None,
            "tftp_server_source": None,
            "bootfile": None,
            "bootfile_source": None,
        }

        opt66 = options.get(66)
        if opt66:
            result["tftp_server"] = opt66.rstrip(b"\x00").decode("utf-8", errors="replace")
            result["tftp_server_source"] = "option 66"
        elif siaddr != "0.0.0.0":
            result["tftp_server"] = siaddr
            result["tftp_server_source"] = "siaddr"

        opt67 = options.get(67)
        if opt67:
            result["bootfile"] = opt67.rstrip(b"\x00").decode("utf-8", errors="replace")
            result["bootfile_source"] = "option 67"
        elif bootp_file:
            result["bootfile"] = bootp_file
            result["bootfile_source"] = "BOOTP file field"

        # Option 43 (PXE vendor-specific): fallback for pxe-service proxy responses
        opt43 = options.get(43)
        if opt43 and not result["tftp_server"]:
            pxe = self._parse_pxe_opt43(opt43)
            if pxe.get("server"):
                result["tftp_server"] = pxe["server"]
                result["tftp_server_source"] = "option 43 (PXE boot server)"

        return result

    def check_network(
        self, interface: Optional[str] = None, expected_server_ip: str = "192.168.10.32"
    ) -> Dict[str, Any]:
        """Probe DHCP for three client types (BIOS, UEFI, iPXE) simultaneously."""
        import random
        import socket as _socket
        import struct
        import time

        iface = interface or self._get_default_iface()

        # Three probe types matching typical router dnsmasq PXE config.
        # Boot file names are informational only — users can use any valid bootloader.
        # We only check that the TFTP server (or HTTP URL) points to expected_server_ip.
        probe_defs = [
            {
                "name": "bios",
                "label": "BIOS (arch 0)",
                "arch": 0x0000,
                "is_ipxe": False,
            },
            {
                "name": "uefi",
                "label": "UEFI64 (arch 7)",
                "arch": 0x0007,
                "is_ipxe": False,
            },
            {
                "name": "ipxe",
                "label": "iPXE (option 175)",
                "arch": 0x0000,
                "is_ipxe": True,
            },
            {
                "name": "dhcp",
                "label": "DHCP (IP assignment)",
                "arch": None,  # plain DISCOVER — no PXE options, proxy ignores this
                "is_ipxe": False,
                "is_plain": True,
            },
        ]

        for p in probe_defs:
            p["xid"] = random.randint(1, 0x7FFFFFFF)
            p["mac"] = bytes(
                [
                    0x00,
                    0x50,
                    0x56,
                    random.randint(0, 255),
                    random.randint(0, 255),
                    random.randint(0, 255),
                ]
            )
            p["offers"] = []  # collect ALL offers (may get both proxy + router)

        # Receive socket: regular UDP on port 68 to capture broadcast DHCP OFFERs
        recv_sock = _socket.socket(_socket.AF_INET, _socket.SOCK_DGRAM, _socket.IPPROTO_UDP)
        recv_sock.setsockopt(_socket.SOL_SOCKET, _socket.SO_BROADCAST, 1)
        recv_sock.setsockopt(_socket.SOL_SOCKET, _socket.SO_REUSEADDR, 1)
        try:
            recv_sock.setsockopt(_socket.SOL_SOCKET, _socket.SO_REUSEPORT, 1)
        except AttributeError:
            pass

        try:
            recv_sock.bind(("", 68))
        except PermissionError:
            recv_sock.close()
            return {
                "status": "error",
                "message": "Cannot bind to port 68 — requires NET_ADMIN capability",
                "interface": iface,
                "suggestions": [
                    "Ensure the container has cap_add: [NET_ADMIN] in docker-compose.yml"
                ],
            }
        except OSError as exc:
            recv_sock.close()
            return {
                "status": "error",
                "message": f"Cannot bind to port 68: {exc}",
                "interface": iface,
                "suggestions": ["Port 68 may already be in use by another DHCP client"],
            }

        # Send socket: raw IP socket so we can use source IP 0.0.0.0.
        # This prevents router rate-limiting (router sees each probe as a fresh client).
        # Falls back to regular UDP if raw sockets are unavailable.
        try:
            send_sock = _socket.socket(_socket.AF_INET, _socket.SOCK_RAW, _socket.IPPROTO_RAW)
            send_sock.setsockopt(_socket.IPPROTO_IP, _socket.IP_HDRINCL, 1)
            send_sock.setsockopt(_socket.SOL_SOCKET, _socket.SO_BROADCAST, 1)
            use_raw = True
        except (PermissionError, OSError):
            send_sock = recv_sock  # reuse recv socket, fallback to regular UDP
            use_raw = False

        # Inter-probe delays (seconds). ASUS/dnsmasq rate-limits DHCP responses per
        # source IP — each probe must wait for the router to reset before the next.
        # Other DHCP servers (ISC, Windows, pfSense, Mikrotik) don't have this limit
        # and will respond instantly; the delays just add a small overhead for them.
        # Plain DHCP probe (4th) uses a different MAC and no PXE vendor class, so
        # it doesn't trigger PXE-specific rate limiting — no extra delay needed.
        probe_delays = [5.0, 10.0, 0.0, 0.0]  # after BIOS, UEFI, iPXE, plain

        try:
            for p, delay_after in zip(probe_defs, probe_delays):
                # Send one DISCOVER
                dhcp_pkt = self._build_discover(p["mac"], p["xid"], p["arch"], p["is_ipxe"])
                if use_raw:
                    send_sock.sendto(self._wrap_ip_udp(dhcp_pkt), ("255.255.255.255", 0))
                else:
                    recv_sock.sendto(dhcp_pkt, ("255.255.255.255", 67))

                # Collect all OFFER responses within timeout window.
                # In proxy DHCP mode a client can receive two OFFERs:
                #   1. Router DHCP  → real IP (yiaddr != 0.0.0.0)
                #   2. Our proxy    → yiaddr = 0.0.0.0, option 43 PXE info
                # Collecting both lets us detect the conflict scenario.
                deadline = time.monotonic() + self.timeout
                while time.monotonic() < deadline:
                    recv_sock.settimeout(max(0.1, deadline - time.monotonic()))
                    try:
                        data, addr = recv_sock.recvfrom(4096)
                    except _socket.timeout:
                        break
                    if len(data) < 240 or data[0] != 2:
                        continue
                    resp_xid = struct.unpack("!I", data[4:8])[0]
                    if resp_xid != p["xid"]:
                        continue
                    p["offers"].append(self._parse_offer(data, addr))

                # Wait between probes so the router's rate-limit can reset
                if delay_after > 0:
                    time.sleep(delay_after)

        except PermissionError:
            return {
                "status": "error",
                "message": "Insufficient privileges to send DHCP broadcast",
                "interface": iface,
                "suggestions": ["Ensure the container has NET_ADMIN and NET_RAW capabilities"],
            }
        except Exception as exc:
            return {
                "status": "error",
                "message": f"DHCP validation failed: {exc}",
                "error_type": type(exc).__name__,
                "interface": iface,
                "suggestions": ["Check network connectivity and interface name"],
            }
        finally:
            recv_sock.close()
            if use_raw and send_sock is not recv_sock:
                send_sock.close()

        # --- Evaluate each probe ---
        probes_out: Dict[str, Any] = {}
        for p in probe_defs:
            offers = p["offers"]

            # Plain DHCP probe: only checks that a real IP-assignment DHCP server exists.
            # dnsmasq in proxy mode does NOT respond to plain DISCOVERs, so only the
            # router (or another DHCP server) will answer.  yiaddr must be a real IP.
            if p.get("is_plain"):
                if not offers:
                    probes_out[p["name"]] = {
                        "label": p["label"],
                        "status": "warning",
                        "message": (
                            "No response — no IP-assignment DHCP server detected. "
                            "PXE clients will not receive an IP address."
                        ),
                    }
                else:
                    real_offer = next((o for o in offers if o["offered_ip"] != "0.0.0.0"), None)
                    if real_offer:
                        probes_out[p["name"]] = {
                            "label": p["label"],
                            "status": "success",
                            "message": f"IP offer received ({real_offer['offered_ip']})",
                            "dhcp_server": real_offer["dhcp_server"],
                            "offered_ip": real_offer["offered_ip"],
                        }
                    else:
                        probes_out[p["name"]] = {
                            "label": p["label"],
                            "status": "warning",
                            "message": (
                                "Only proxy DHCP responded (0.0.0.0) — "
                                "no real IP-assignment DHCP server found. "
                                "PXE clients will not receive an IP address."
                            ),
                            "dhcp_server": offers[0]["dhcp_server"],
                            "offered_ip": "0.0.0.0",
                        }
                continue

            # PXE probes (BIOS / UEFI / iPXE)
            if not offers:
                probes_out[p["name"]] = {"label": p["label"], "status": "no_response"}
                continue

            # Pick the best offer for PXE evaluation:
            # prefer our proxy (0.0.0.0) over the router if both responded —
            # the proxy response contains the authoritative PXE boot info.
            proxy_offer = next((o for o in offers if o["offered_ip"] == "0.0.0.0"), None)
            router_offer = next((o for o in offers if o["offered_ip"] != "0.0.0.0"), None)
            offer = proxy_offer or router_offer

            issues: List[str] = []
            warnings_list: List[str] = []

            # Conflict: both proxy AND router responded with explicit PXE options.
            # Router simply giving an IP alongside the proxy is normal proxy DHCP behaviour —
            # dnsmasq always sets siaddr to its own IP, which is NOT an explicit PXE config.
            # Only flag a conflict when the router's offer has option 66 (TFTP server name)
            # or option 67 (bootfile), meaning an administrator explicitly configured PXE
            # on the router AND our proxy is also active — two competing PXE sources.
            router_has_pxe = router_offer and (
                router_offer.get("bootfile")
                or router_offer.get("tftp_server_source") == "option 66"
            )
            if proxy_offer and router_has_pxe:
                warnings_list.append(
                    f"Both proxy DHCP ({proxy_offer['dhcp_server']}) and router DHCP "
                    f"({router_offer['dhcp_server']}) are providing PXE options — disable "
                    "options 66/67 on the router when using Proxy DHCP to avoid conflicts"
                )

            tftp_server = offer["tftp_server"]
            bootfile = offer["bootfile"]

            if p["is_ipxe"]:
                # iPXE clients get a boot URL (HTTP) — check it points to our server
                if not bootfile:
                    issues.append("No boot URL returned (expected HTTP URL for iPXE clients)")
                elif not bootfile.startswith(("http://", "https://")):
                    warnings_list.append(
                        f"Boot response is {bootfile!r} — expected an HTTP/HTTPS URL for iPXE"
                    )
                elif expected_server_ip not in bootfile:
                    warnings_list.append(
                        f"Boot URL {bootfile!r} does not reference expected server"
                        f" {expected_server_ip!r}"
                    )
            else:
                # BIOS / UEFI: validate TFTP server points to our station.
                # Boot file name is informational — user may use any valid bootloader.
                # When proxy DHCP uses pxe-service, bootfile is NOT in the DHCP packet
                # (the client discovers it via PXE boot negotiation with the TFTP server).
                if not tftp_server:
                    issues.append("No TFTP server in response (option 66 / siaddr / option 43)")
                elif tftp_server != expected_server_ip:
                    warnings_list.append(
                        f"TFTP server is {tftp_server!r} ({offer.get('tftp_server_source', '')}), "
                        f"expected {expected_server_ip!r}"
                    )
                # No bootfile in DHCP is expected with pxe-service proxy mode —
                # not an error, not a warning, the client negotiates it via TFTP.

            if not issues and not warnings_list:
                probe_status, probe_msg = "success", "Correctly configured"
            elif issues:
                probe_status, probe_msg = "not_configured", "; ".join(issues)
            else:
                probe_status, probe_msg = "warning", "; ".join(warnings_list)

            probe_result: Dict[str, Any] = {
                "label": p["label"],
                "status": probe_status,
                "message": probe_msg,
                "dhcp_server": offer["dhcp_server"],
                "offered_ip": offer["offered_ip"],
            }
            if proxy_offer and router_has_pxe:
                probe_result["conflict"] = {
                    "proxy": proxy_offer["dhcp_server"],
                    "router": router_offer["dhcp_server"],
                }
            if p["is_ipxe"] and bootfile:
                probe_result["boot_url"] = bootfile
            if not p["is_ipxe"]:
                if tftp_server:
                    probe_result["tftp_server"] = tftp_server
                if bootfile:
                    probe_result["bootfile"] = bootfile
            if issues:
                probe_result["issues"] = issues
            if warnings_list:
                probe_result["warnings"] = warnings_list
            probes_out[p["name"]] = probe_result

        # --- Overall status ---
        # Evaluate PXE probes (BIOS/UEFI/iPXE) and plain DHCP probe separately.
        pxe_statuses = {
            probes_out[n].get("status") for n in ("bios", "uefi", "ipxe") if n in probes_out
        }
        dhcp_probe_status = probes_out.get("dhcp", {}).get("status")

        if pxe_statuses == {"no_response"}:
            overall_status = "no_response"
            overall_message = "No DHCP OFFER received from network"
        elif (
            "success" in pxe_statuses
            and "not_configured" not in pxe_statuses
            and "warning" not in pxe_statuses
        ):
            if dhcp_probe_status == "success":
                overall_status = "success"
                overall_message = "PXE boot and IP assignment are correctly configured"
            elif dhcp_probe_status == "warning":
                overall_status = "warning"
                overall_message = (
                    "PXE boot is configured but no IP-assignment DHCP server was detected — "
                    "clients will not receive an IP address"
                )
            else:
                # dhcp probe absent (shouldn't happen) — treat PXE-only result as success
                overall_status = "success"
                overall_message = "DHCP server is correctly configured for PXE boot"
        elif "success" in pxe_statuses or "warning" in pxe_statuses:
            overall_status = "warning"
            overall_message = "DHCP server has PXE configuration but with potential issues"
        else:
            overall_status = "not_configured"
            overall_message = (
                "DHCP server is present but not configured for PXE boot. "
                "This is expected when using Proxy DHCP."
            )

        # Backward-compatible top-level `detected` from BIOS probe
        bios = probes_out.get("bios", {})
        detected: Dict[str, Any] = {}
        if bios.get("dhcp_server"):
            detected["dhcp_server"] = bios["dhcp_server"]
        if bios.get("offered_ip"):
            detected["offered_ip"] = bios["offered_ip"]
        if bios.get("tftp_server"):
            detected["option_66_tftp_server"] = bios["tftp_server"]
        if bios.get("bootfile"):
            detected["option_67_bootfile"] = bios["bootfile"]

        scenario = self._detect_scenario(probes_out, expected_server_ip)
        recommendations = self._build_recommendations(scenario, probes_out, expected_server_ip)

        return {
            "status": overall_status,
            "message": overall_message,
            "interface": iface,
            "detected": detected,
            "probes": probes_out,
            "issues": [m for p in probes_out.values() for m in p.get("issues", [])],
            "warnings": [m for p in probes_out.values() for m in p.get("warnings", [])],
            "scenario": scenario,
            "recommendations": recommendations,
        }

    def _detect_scenario(self, probes_out: Dict[str, Any], expected_server_ip: str) -> str:
        """Classify the network's DHCP/PXE state into one of the known scenario keys."""
        pxe_names = ("bios", "uefi", "ipxe")
        pxe_probes = [probes_out[n] for n in pxe_names if n in probes_out]
        dhcp_probe = probes_out.get("dhcp", {})

        pxe_statuses = {p.get("status") for p in pxe_probes}
        dhcp_status = dhcp_probe.get("status")

        # 1. No DHCP at all — all PXE probes no_response AND no IP-assignment DHCP
        if pxe_statuses <= {"no_response"} and dhcp_status != "success":
            return "no_dhcp"

        # 2. Conflict — both proxy AND router PXE responded to at least one probe
        if any("conflict" in p for p in pxe_probes):
            return "conflict"

        # 3a. Proxy OK: BIOS/UEFI succeed in proxy mode (offered_ip=0.0.0.0), iPXE probe may be
        # not_configured because proxy sends a TFTP filename rather than an HTTP URL — expected.
        bios_ok = probes_out.get("bios", {}).get("status") == "success"
        uefi_ok = probes_out.get("uefi", {}).get("status") == "success"
        bios_proxy = probes_out.get("bios", {}).get("offered_ip") == "0.0.0.0"
        uefi_proxy = probes_out.get("uefi", {}).get("offered_ip") == "0.0.0.0"
        if (bios_ok or uefi_ok) and (bios_proxy or uefi_proxy) and dhcp_status == "success":
            return "proxy_ok"

        # 3b. All PXE probes successful AND IP-assignment DHCP present
        if pxe_statuses == {"success"} and dhcp_status == "success":
            # proxy_ok when any PXE offer came from a proxy (offered_ip == 0.0.0.0)
            if any(p.get("offered_ip") == "0.0.0.0" for p in pxe_probes):
                return "proxy_ok"
            return "router_ok"

        # 4. All PXE probes successful but no IP-assignment DHCP → clients won't get IPs
        if pxe_statuses == {"success"} and dhcp_status in ("warning", None):
            return "proxy_no_dhcp"

        # 5. DHCP gives IPs but no PXE anywhere
        if pxe_statuses <= {"no_response", "not_configured"} and dhcp_status == "success":
            return "no_pxe"

        # 6. PXE configured but TFTP/boot URL points to wrong server
        for p in pxe_probes:
            if p.get("status") == "warning":
                probe_warnings = p.get("warnings", [])
                if any(
                    "TFTP server" in w or "does not reference" in w or "Boot URL" in w
                    for w in probe_warnings
                ):
                    return "wrong_server"

        return "partial"

    def _build_recommendations(
        self, scenario: str, probes_out: Dict[str, Any], expected_server_ip: str
    ) -> List[Dict[str, Any]]:
        """Return actionable recommendations for the detected scenario."""
        recs: List[Dict[str, Any]] = []

        def rec(title: str, description: str, severity: str, fix_url=None, fix_label=None):
            recs.append(
                {
                    "title": title,
                    "description": description,
                    "severity": severity,
                    "fix_url": fix_url,
                    "fix_method": "POST",
                    "fix_label": fix_label,
                }
            )

        if scenario == "proxy_ok":
            rec(
                "Proxy DHCP active",
                "Proxy DHCP is active. Clients get IP from router, PXE from proxy.",
                "success",
            )

        elif scenario == "router_ok":
            rec(
                "Router DHCP correctly configured",
                "Router DHCP is providing correct PXE configuration.",
                "success",
            )

        elif scenario == "conflict":
            rec(
                "Disable router PXE options",
                "Disable PXE options (66/67) on your router to use Proxy DHCP exclusively.",
                "warning",
            )
            rec(
                "Stop Proxy DHCP",
                "Or stop Proxy DHCP to use router PXE only.",
                "info",
                fix_url="/api/proxy-dhcp/stop",
                fix_label="Stop Proxy DHCP",
            )

        elif scenario == "no_pxe":
            rec(
                "No PXE configuration found",
                "No PXE boot configuration found. Clients will get an IP but cannot boot.",
                "error",
            )
            rec(
                "Enable Proxy DHCP",
                "Enable Proxy DHCP — no router changes needed.",
                "info",
                fix_url="/api/proxy-dhcp/start",
                fix_label="Start Proxy DHCP",
            )
            rec(
                "Configure router manually",
                f"Or configure router: option 66 = {expected_server_ip}, "
                "option 67 = undionly.kpxe / ipxe.efi",
                "info",
            )

        elif scenario == "wrong_server":
            wrong_ip: Optional[str] = None
            for name in ("bios", "uefi", "ipxe"):
                p = probes_out.get(name, {})
                if p.get("tftp_server") and p["tftp_server"] != expected_server_ip:
                    wrong_ip = p["tftp_server"]
                    break
            ip_desc = f"TFTP server is {wrong_ip!r}" if wrong_ip else "PXE is configured"
            rec(
                "Wrong PXE server",
                f"{ip_desc}, not {expected_server_ip!r}. "
                "Update router option 66 or enable Proxy DHCP.",
                "warning",
                fix_url="/api/proxy-dhcp/start",
                fix_label="Start Proxy DHCP",
            )

        elif scenario == "proxy_no_dhcp":
            rec(
                "No IP-assignment DHCP server",
                "Proxy DHCP responds to PXE but no router DHCP found — clients will not receive "
                "IP addresses. Check your router's DHCP server.",
                "error",
            )

        elif scenario == "no_dhcp":
            rec(
                "No DHCP server found",
                "No DHCP server found. Check router is running and DHCP is enabled.",
                "error",
            )

        elif scenario == "partial":
            for name in ("bios", "uefi", "ipxe"):
                p = probes_out.get(name, {})
                if p.get("status") in ("no_response", "not_configured", "warning"):
                    rec(
                        f"{p.get('label', name)} not configured",
                        p.get("message", "No PXE response for this client type."),
                        "warning",
                    )

        return recs
