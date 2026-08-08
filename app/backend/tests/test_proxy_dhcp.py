"""Tests for ProxyDHCPManager's dnsmasq config generation.

Covers pure string generation (generate_conf) only — no real dnsmasq process,
subprocess, or network I/O involved.
"""

from app.backend.proxy_dhcp import ProxyDHCPManager, ProxyDHCPSettings


class TestGenerateConf:
    def setup_method(self):
        self.manager = ProxyDHCPManager()

    def test_bios_and_uefi_enabled_by_default(self):
        settings = ProxyDHCPSettings(server_ip="10.0.0.1")
        conf = self.manager.generate_conf(settings)
        assert "undionly.kpxe" in conf
        assert "autoexec.ipxe" in conf
        assert "x86-64_EFI" in conf
        assert "BC_EFI" in conf
        assert "dhcp-range=10.0.0.0,proxy" in conf

    def test_bios_only(self):
        settings = ProxyDHCPSettings(server_ip="10.0.0.1", support_bios=True, support_uefi=False)
        conf = self.manager.generate_conf(settings)
        assert "undionly.kpxe" in conf
        assert "x86-64_EFI" not in conf

    def test_uefi_only(self):
        settings = ProxyDHCPSettings(server_ip="10.0.0.1", support_bios=False, support_uefi=True)
        conf = self.manager.generate_conf(settings)
        # "undionly.kpxe" also appears in a static explanatory comment regardless of
        # settings — assert on the actual pxe-service line instead.
        assert "pxe-service=tag:!ipxe,x86PC," not in conf
        assert "x86-64_EFI" in conf

    def test_explicit_subnet_overrides_derived(self):
        settings = ProxyDHCPSettings(server_ip="10.0.0.1", subnet="192.168.99.0")
        conf = self.manager.generate_conf(settings)
        assert "dhcp-range=192.168.99.0,proxy" in conf
        assert "10.0.0.0" not in conf

    def test_http_boot_omitted_by_default(self):
        settings = ProxyDHCPSettings(server_ip="10.0.0.1")
        conf = self.manager.generate_conf(settings)
        assert "HTTPClient" not in conf
        assert "dhcp-vendorclass" not in conf

    def test_http_boot_included_when_enabled(self):
        settings = ProxyDHCPSettings(server_ip="10.0.0.1", http_port=9021, support_http_boot=True)
        conf = self.manager.generate_conf(settings)
        assert "dhcp-vendorclass=set:httpclient,HTTPClient" in conf
        assert 'dhcp-option-force=tag:httpclient,60,"HTTPClient"' in conf
        assert "dhcp-boot=tag:httpclient,http://10.0.0.1:9021/tftp/ipxe.efi,,10.0.0.1" in conf

    def test_http_boot_independent_of_bios_uefi_flags(self):
        settings = ProxyDHCPSettings(
            server_ip="10.0.0.1",
            support_bios=False,
            support_uefi=False,
            support_http_boot=True,
        )
        conf = self.manager.generate_conf(settings)
        assert "pxe-service=tag:!ipxe,x86PC," not in conf
        assert "x86-64_EFI" not in conf
        assert "HTTPClient" in conf


class TestDeriveSubnet:
    def test_derive_subnet_zeroes_last_octet(self):
        manager = ProxyDHCPManager()
        assert manager._derive_subnet("192.168.10.55") == "192.168.10.0"

    def test_derive_subnet_passthrough_on_malformed_ip(self):
        manager = ProxyDHCPManager()
        assert manager._derive_subnet("not-an-ip") == "not-an-ip"
