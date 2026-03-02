"""Tests for DHCPConfigGenerator and DHCPValidator."""

import pytest

from app.backend.dhcp_helper import DHCPConfig, DHCPConfigGenerator


class TestDHCPConfig:
    def test_default_values(self):
        config = DHCPConfig(pxe_server_ip="10.0.0.1")
        assert config.pxe_server_ip == "10.0.0.1"
        assert config.http_port == 9021
        assert config.tftp_port == 69
        assert config.server_type == "dnsmasq"

    def test_custom_values(self):
        config = DHCPConfig(
            pxe_server_ip="192.168.1.50",
            http_port=8080,
            tftp_port=70,
            server_type="isc-dhcp",
        )
        assert config.pxe_server_ip == "192.168.1.50"
        assert config.http_port == 8080
        assert config.tftp_port == 70
        assert config.server_type == "isc-dhcp"


class TestDHCPConfigGenerator:
    def setup_method(self):
        self.generator = DHCPConfigGenerator()
        self.config = DHCPConfig(pxe_server_ip="10.0.0.5", http_port=9021)

    def test_generate_returns_dict_with_required_keys(self):
        result = self.generator.generate(self.config)
        assert "type" in result
        assert "config" in result
        assert "description" in result
        assert "filename" in result

    def test_generate_dnsmasq(self):
        result = self.generator.generate(self.config)
        assert result["type"] == "dnsmasq"
        assert "10.0.0.5" in result["config"]
        assert "9021" in result["config"]
        assert result["filename"] == "dnsmasq.conf"

    def test_generate_isc_dhcp(self):
        config = DHCPConfig(pxe_server_ip="10.0.0.5", server_type="isc-dhcp")
        result = self.generator.generate(config)
        assert result["type"] == "isc-dhcp"
        assert "10.0.0.5" in result["config"]
        assert result["filename"] == "dhcpd.conf"

    def test_generate_mikrotik(self):
        config = DHCPConfig(pxe_server_ip="10.0.0.5", server_type="mikrotik")
        result = self.generator.generate(config)
        assert result["type"] == "mikrotik"
        assert "10.0.0.5" in result["config"]
        assert result["filename"] == "mikrotik-commands.txt"

    def test_generate_windows(self):
        config = DHCPConfig(pxe_server_ip="10.0.0.5", server_type="windows")
        result = self.generator.generate(config)
        assert result["type"] == "windows"
        assert "10.0.0.5" in result["config"]
        assert result["filename"] == "windows-dhcp-setup.txt"

    def test_generate_unknown_type_raises(self):
        config = DHCPConfig(pxe_server_ip="10.0.0.5", server_type="unknown-dhcp")
        with pytest.raises(ValueError, match="Unknown server type"):
            self.generator.generate(config)

    def test_list_server_types_returns_all_four(self):
        types = self.generator.list_server_types()
        assert len(types) == 4
        ids = [t["id"] for t in types]
        assert "dnsmasq" in ids
        assert "isc-dhcp" in ids
        assert "mikrotik" in ids
        assert "windows" in ids

    def test_list_server_types_have_required_keys(self):
        types = self.generator.list_server_types()
        for server_type in types:
            assert "id" in server_type
            assert "name" in server_type
            assert "description" in server_type

    def test_dnsmasq_config_contains_pxe_options(self):
        result = self.generator.generate(self.config)
        config_text = result["config"]
        # Should contain iPXE option 175 detection
        assert "175" in config_text
        # Should contain both UEFI and BIOS boot entries
        assert "ipxe.efi" in config_text
        assert "undionly.kpxe" in config_text

    def test_isc_dhcp_config_contains_arch_detection(self):
        config = DHCPConfig(pxe_server_ip="10.0.0.5", server_type="isc-dhcp")
        result = self.generator.generate(config)
        config_text = result["config"]
        assert "iPXE" in config_text
        assert "filename" in config_text
