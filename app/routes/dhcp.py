"""DHCP configuration helper routes."""

from fastapi import APIRouter, HTTPException

from app.backend.dhcp_helper import DHCPConfig, DHCPConfigGenerator, DHCPValidator
from app.routes.state import SETTINGS_FILE, SettingsModel

dhcp_router = APIRouter(prefix="/api/dhcp", tags=["dhcp"])
dhcp_generator = DHCPConfigGenerator()
dhcp_validator = DHCPValidator()


@dhcp_router.get("/server-types")
def list_dhcp_server_types():
    """List supported DHCP server types."""
    return {"server_types": dhcp_generator.list_server_types()}


@dhcp_router.post("/config/generate")
def generate_dhcp_config(
    server_type: str = "dnsmasq",
    pxe_server_ip: str = "192.168.10.32",
    http_port: int = 9021,
    tftp_port: int = 69,
):
    """Generate DHCP configuration for specified server type."""
    try:
        config = DHCPConfig(
            pxe_server_ip=pxe_server_ip,
            http_port=http_port,
            tftp_port=tftp_port,
            server_type=server_type,
        )
        result = dhcp_generator.generate(config)
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@dhcp_router.get("/validate/network")
def validate_network_dhcp(expected_server_ip: str = ""):
    """Check and validate DHCP configuration on the network."""
    if not expected_server_ip:
        try:
            import json

            data = json.loads(SETTINGS_FILE.read_text())
            expected_server_ip = SettingsModel(**data).server_ip
        except Exception:
            expected_server_ip = SettingsModel().server_ip
    result = dhcp_validator.check_network(expected_server_ip=expected_server_ip)
    return result
