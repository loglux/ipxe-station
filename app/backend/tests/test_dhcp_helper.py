"""Tests for DHCPConfigGenerator and DHCPValidator."""

import pytest

from app.backend.dhcp_helper import DHCPConfig, DHCPConfigGenerator, DHCPValidator


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


class TestDHCPValidatorConfig:
    """Tests for DHCPValidator.validate_config() (pure logic, no network)."""

    def setup_method(self):
        self.validator = DHCPValidator()
        self.expected_ip = "192.168.10.32"

    def test_valid_config_all_options_correct(self):
        detected = {
            "option_66": self.expected_ip,
            "option_67": "undionly.kpxe",
            "option_175": "present",
        }
        result = self.validator.validate_config(detected, self.expected_ip)
        assert result["valid"] is True
        assert len(result["issues"]) == 0

    def test_missing_option_66(self):
        detected = {"option_67": "undionly.kpxe"}
        result = self.validator.validate_config(detected, self.expected_ip)
        assert result["valid"] is False
        assert any("66" in issue for issue in result["issues"])

    def test_wrong_option_66_ip(self):
        detected = {
            "option_66": "192.168.1.100",  # Wrong IP
            "option_67": "undionly.kpxe",
        }
        result = self.validator.validate_config(detected, self.expected_ip)
        assert result["valid"] is False
        assert any("66" in issue for issue in result["issues"])

    def test_missing_option_67(self):
        detected = {"option_66": self.expected_ip}
        result = self.validator.validate_config(detected, self.expected_ip)
        assert result["valid"] is False
        assert any("67" in issue for issue in result["issues"])

    def test_invalid_bootfile_is_warning(self):
        detected = {
            "option_66": self.expected_ip,
            "option_67": "pxelinux.0",  # Not an iPXE binary
        }
        result = self.validator.validate_config(detected, self.expected_ip)
        # pxelinux.0 triggers a warning, not a fatal error
        assert len(result["warnings"]) > 0

    def test_uefi_bootfile_accepted(self):
        detected = {
            "option_66": self.expected_ip,
            "option_67": "ipxe.efi",
            "option_175": "present",
        }
        result = self.validator.validate_config(detected, self.expected_ip)
        assert result["valid"] is True

    def test_missing_option_175_is_warning(self):
        detected = {
            "option_66": self.expected_ip,
            "option_67": "undionly.kpxe",
            # No option_175
        }
        result = self.validator.validate_config(detected, self.expected_ip)
        # Should warn but still be valid
        assert len(result["warnings"]) > 0
        assert any("175" in w for w in result["warnings"])
