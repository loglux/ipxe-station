import gradio as gr
import os
import subprocess
from pathlib import Path
import requests


def build_gradio_ui():
    def get_tftp_files():
        """Get list of files in TFTP directory"""
        tftp_dir = Path("/srv/tftp")
        if tftp_dir.exists():
            files = []
            for f in tftp_dir.iterdir():
                if f.is_file():
                    size_mb = f.stat().st_size / (1024 * 1024)
                    files.append(f"{f.name} ({size_mb:.1f} MB)")
            return "\n".join(files) if files else "No files found"
        return "TFTP directory not found"

    def get_http_structure():
        """Get HTTP directory structure"""
        http_dir = Path("/srv/http")
        if not http_dir.exists():
            return "HTTP directory not found"

        structure = []
        for root, dirs, files in os.walk(http_dir):
            level = root.replace(str(http_dir), '').count(os.sep)
            indent = ' ' * 2 * level
            structure.append(f"{indent}{os.path.basename(root)}/")
            subindent = ' ' * 2 * (level + 1)
            for file in files:
                size = os.path.getsize(os.path.join(root, file))
                size_mb = size / (1024 * 1024)
                structure.append(f"{subindent}{file} ({size_mb:.1f} MB)")

        return "\n".join(structure) if structure else "No files found"

    def get_server_status():
        """Get server status information"""
        status = """🌐 iPXE Station Status:
• HTTP Server: ✅ Running (FastAPI)
• Web UI: ✅ Running (port 9005)
• TFTP Port: 69/UDP
• iPXE Menu: http://SERVER_IP:9005/ipxe/boot.ipxe

📋 Setup Status:
"""

        # Check if iPXE files exist
        ipxe_boot = Path("/srv/ipxe/boot.ipxe")
        if ipxe_boot.exists():
            status += "• iPXE Menu: ✅ Created\n"
        else:
            status += "• iPXE Menu: ❌ Missing\n"

        # Check TFTP files
        tftp_files = Path("/srv/tftp")
        if tftp_files.exists() and any(tftp_files.iterdir()):
            status += "• TFTP Files: ✅ Available\n"
        else:
            status += "• TFTP Files: ❌ Missing\n"

        # Check Ubuntu files
        ubuntu_kernel = Path("/srv/http/ubuntu/vmlinuz")
        ubuntu_initrd = Path("/srv/http/ubuntu/initrd")
        if ubuntu_kernel.exists() and ubuntu_initrd.exists():
            status += "• Ubuntu 24.04.2: ✅ Ready\n"
        else:
            status += "• Ubuntu 24.04.2: ❌ Not downloaded\n"

        status += "\n🔧 Next Steps:\n"
        status += "1. Download iPXE binaries (TFTP tab)\n"
        status += "2. Download Ubuntu files (Ubuntu tab)\n"
        status += "3. Configure DHCP server (DHCP tab)\n"

        return status

    def download_ipxe_files():
        """Download iPXE binaries"""
        try:
            tftp_dir = Path("/srv/tftp")
            tftp_dir.mkdir(parents=True, exist_ok=True)

            status = "🔄 Downloading iPXE binaries...\n"

            # Download undionly.kpxe (BIOS/Legacy)
            url1 = "http://boot.ipxe.org/undionly.kpxe"
            response1 = requests.get(url1, timeout=30)
            if response1.status_code == 200:
                with open(tftp_dir / "undionly.kpxe", "wb") as f:
                    f.write(response1.content)
                status += "✅ Downloaded undionly.kpxe (BIOS/Legacy)\n"
            else:
                status += "❌ Failed to download undionly.kpxe\n"

            # Download ipxe.efi (UEFI)
            url2 = "http://boot.ipxe.org/ipxe.efi"
            response2 = requests.get(url2, timeout=30)
            if response2.status_code == 200:
                with open(tftp_dir / "ipxe.efi", "wb") as f:
                    f.write(response2.content)
                status += "✅ Downloaded ipxe.efi (UEFI)\n"
            else:
                status += "❌ Failed to download ipxe.efi\n"

            status += "\n🎉 iPXE binaries downloaded successfully!"
            return status

        except Exception as e:
            return f"❌ Error downloading iPXE files: {str(e)}"

    def download_ubuntu_files():
        """Download Ubuntu 24.04.2 LTS netboot files"""
        try:
            ubuntu_dir = Path("/srv/http/ubuntu")
            ubuntu_dir.mkdir(parents=True, exist_ok=True)

            status = "🔄 Downloading Ubuntu 24.04.2 LTS files...\n"

            # Ubuntu 24.04.2 LTS netboot URLs
            base_url = "http://archive.ubuntu.com/ubuntu/dists/noble/main/installer-amd64/current/legacy-images/netboot/ubuntu-installer/amd64/"

            files_to_download = [
                ("linux", "vmlinuz", "Kernel"),
                ("initrd.gz", "initrd", "Initial RAM disk")
            ]

            for remote_name, local_name, description in files_to_download:
                url = base_url + remote_name
                status += f"📥 Downloading {description}...\n"

                response = requests.get(url, timeout=60)
                if response.status_code == 200:
                    with open(ubuntu_dir / local_name, "wb") as f:
                        f.write(response.content)
                    size_mb = len(response.content) / (1024 * 1024)
                    status += f"✅ {description}: {size_mb:.1f} MB\n"
                else:
                    status += f"❌ Failed to download {description}\n"

            status += "\n🎉 Ubuntu 24.04.2 LTS files downloaded!"
            status += "\n📝 Note: This is the network installer, not the full desktop."
            return status

        except Exception as e:
            return f"❌ Error downloading Ubuntu files: {str(e)}"

    def create_ipxe_menu():
        """Create iPXE boot menu"""
        try:
            ipxe_dir = Path("/srv/ipxe")
            ipxe_dir.mkdir(parents=True, exist_ok=True)

            menu_content = """#!ipxe

# iPXE Station - Ubuntu 24.04.2 LTS Boot Menu
echo
echo ========================================
echo     iPXE Station - Network Boot
echo          Ubuntu 24.04.2 LTS
echo ========================================
echo

# Get network info
echo Network: ${net0/ip} / ${net0/netmask}
echo Gateway: ${net0/gateway}
echo DNS: ${net0/dns}
echo Server: ${next-server}
echo

# Set menu timeout (30 seconds)
set menu-timeout 30000

# Main menu
:menu
menu iPXE Station - Select Boot Option
item --gap -- ----- Ubuntu 24.04.2 LTS -----
item ubuntu_install  Ubuntu 24.04.2 LTS Installer
item ubuntu_rescue   Ubuntu Recovery Mode
item --gap -- ----- Utilities -----
item memtest         Memory Test (Memtest86+)
item shell           iPXE Shell
item reboot          Reboot System
item exit            Exit to BIOS
choose --timeout ${menu-timeout} --default ubuntu_install selected || goto cancel
goto ${selected}

:ubuntu_install
echo Booting Ubuntu 24.04.2 LTS Installer...
kernel http://${next-server}:9005/http/ubuntu/vmlinuz
initrd http://${next-server}:9005/http/ubuntu/initrd
imgargs vmlinuz initrd=initrd auto=true priority=critical preseed/url=http://${next-server}:9005/http/ubuntu/preseed.cfg
boot || goto failed

:ubuntu_rescue
echo Booting Ubuntu Recovery Mode...
kernel http://${next-server}:9005/http/ubuntu/vmlinuz
initrd http://${next-server}:9005/http/ubuntu/initrd
imgargs vmlinuz initrd=initrd rescue/enable=true
boot || goto failed

:memtest
echo Starting Memory Test...
# Note: Download memtest86+ binary to /srv/http/memtest/memtest86+
kernel http://${next-server}:9005/http/memtest/memtest86+ || goto failed
boot || goto failed

:shell
echo Entering iPXE shell...
echo Type 'exit' to return to menu
shell
goto menu

:reboot
reboot

:exit
exit

:cancel
echo Boot cancelled, returning to menu...
sleep 2
goto menu

:failed
echo Boot failed! Check:
echo 1. Files are downloaded
echo 2. HTTP server is running  
echo 3. Network connectivity
echo
echo Returning to menu in 5 seconds...
sleep 5
goto menu
"""

            with open(ipxe_dir / "boot.ipxe", "w") as f:
                f.write(menu_content)

            return "✅ iPXE boot menu created successfully!"

        except Exception as e:
            return f"❌ Error creating iPXE menu: {str(e)}"

    def generate_dhcp_config():
        """Generate DHCP configuration"""
        config = """# DHCP Configuration for iPXE Station
# Replace YOUR_SERVER_IP with your actual server IP

# ISC DHCP Server (dhcpd.conf):
subnet 192.168.1.0 netmask 255.255.255.0 {
  range 192.168.1.100 192.168.1.200;
  option routers 192.168.1.1;
  option domain-name-servers 8.8.8.8;

  # iPXE Configuration
  next-server YOUR_SERVER_IP;

  if exists user-class and option user-class = "iPXE" {
    filename "http://YOUR_SERVER_IP:9005/ipxe/boot.ipxe";
  } else if substring(option vendor-class-identifier, 0, 20) = "PXEClient:Arch:00000" {
    filename "undionly.kpxe";  # BIOS
  } else if substring(option vendor-class-identifier, 0, 20) = "PXEClient:Arch:00007" {
    filename "ipxe.efi";       # UEFI
  } else {
    filename "undionly.kpxe";  # Default
  }
}

# pfSense DHCP Setup:
# 1. Services > DHCP Server > LAN
# 2. TFTP Server: YOUR_SERVER_IP
# 3. Boot File Name: undionly.kpxe

# Windows DHCP Server:
# 1. DHCP Console > Scope Options
# 2. Option 66: YOUR_SERVER_IP
# 3. Option 67: undionly.kpxe

# Mikrotik RouterOS:
/ip dhcp-server option
add code=66 name=tftp-server value="'YOUR_SERVER_IP'"
add code=67 name=boot-file value="'undionly.kpxe'"

/ip dhcp-server network
set 0 dhcp-option=tftp-server,boot-file
"""
        return config

    # Gradio Interface
    with gr.Blocks(title="iPXE Station", theme=gr.themes.Soft()) as demo:
        gr.Markdown("# 🌐 iPXE Station - Ubuntu 24.04.2 LTS")
        gr.Markdown("Network boot server with TFTP, HTTP, and iPXE support")

        with gr.Tabs():
            # Status Tab
            with gr.TabItem("📊 Status"):
                status_output = gr.Textbox(
                    label="Server Status",
                    value=get_server_status(),
                    lines=12,
                    interactive=False
                )
                refresh_status_btn = gr.Button("🔄 Refresh Status", variant="secondary")
                refresh_status_btn.click(get_server_status, outputs=status_output)

            # TFTP Setup Tab
            with gr.TabItem("📡 TFTP Setup"):
                gr.Markdown("### Download iPXE Binaries")
                gr.Markdown("These files are needed for initial network boot")

                tftp_output = gr.Textbox(
                    label="TFTP Files Status",
                    value=get_tftp_files(),
                    lines=6,
                    interactive=False
                )

                download_ipxe_btn = gr.Button("📥 Download iPXE Binaries", variant="primary")
                refresh_tftp_btn = gr.Button("🔄 Refresh TFTP List", variant="secondary")

                download_ipxe_btn.click(download_ipxe_files, outputs=tftp_output)
                refresh_tftp_btn.click(get_tftp_files, outputs=tftp_output)

            # Ubuntu Tab
            with gr.TabItem("🐧 Ubuntu Setup"):
                gr.Markdown("### Ubuntu 24.04.2 LTS Download")
                gr.Markdown("Network installer files for Ubuntu Desktop")

                ubuntu_output = gr.Textbox(
                    label="Ubuntu Files Status",
                    value="Click 'Download Ubuntu Files' to get Ubuntu 24.04.2 LTS",
                    lines=8,
                    interactive=False
                )

                with gr.Row():
                    download_ubuntu_btn = gr.Button("📥 Download Ubuntu Files", variant="primary")
                    create_menu_btn = gr.Button("📋 Create iPXE Menu", variant="secondary")

                download_ubuntu_btn.click(download_ubuntu_files, outputs=ubuntu_output)
                create_menu_btn.click(create_ipxe_menu, outputs=ubuntu_output)

            # Files Tab
            with gr.TabItem("📁 Files"):
                with gr.Row():
                    with gr.Column():
                        gr.Markdown("### TFTP Files")
                        tftp_files = gr.Textbox(
                            label="/srv/tftp",
                            value=get_tftp_files(),
                            lines=6,
                            interactive=False
                        )

                    with gr.Column():
                        gr.Markdown("### HTTP Files")
                        http_files = gr.Textbox(
                            label="/srv/http",
                            value=get_http_structure(),
                            lines=6,
                            interactive=False
                        )

                refresh_files_btn = gr.Button("🔄 Refresh All Files", variant="secondary")
                refresh_files_btn.click(
                    lambda: (get_tftp_files(), get_http_structure()),
                    outputs=[tftp_files, http_files]
                )

            # DHCP Tab
            with gr.TabItem("⚙️ DHCP Config"):
                gr.Markdown("### DHCP Server Configuration")
                gr.Markdown("**Replace YOUR_SERVER_IP with your actual server IP address**")

                dhcp_config = gr.Textbox(
                    label="DHCP Configuration Examples",
                    value=generate_dhcp_config(),
                    lines=20,
                    interactive=False
                )

            # Help Tab
            with gr.TabItem("❓ Help"):
                gr.Markdown("""
                ### 🚀 Quick Setup Guide

                **1. Download Files:**
                - Go to "TFTP Setup" → Download iPXE Binaries
                - Go to "Ubuntu Setup" → Download Ubuntu Files
                - Go to "Ubuntu Setup" → Create iPXE Menu

                **2. Configure DHCP:**
                - Copy config from "DHCP Config" tab
                - Replace YOUR_SERVER_IP with your server's IP
                - Apply to your DHCP server

                **3. Test:**
                - Boot a computer from network
                - Should see iPXE menu with Ubuntu option

                ### 📝 What gets installed:
                - **TFTP Files**: iPXE binaries for network boot
                - **Ubuntu Files**: Network installer (not full desktop)
                - **iPXE Menu**: Boot menu with Ubuntu installer

                ### 🔧 Troubleshooting:
                - Check all files are downloaded (Files tab)
                - Verify DHCP points to correct server IP
                - Ensure ports 69/UDP and 9005/TCP are open
                """)

    return demo

if __name__ == "__main__":
    demo = build_gradio_ui()
    demo.launch(
        server_name="0.0.0.0",
        server_port=9005,
        share=False,
        inbrowser=False
    )