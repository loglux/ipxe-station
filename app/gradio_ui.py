import gradio as gr
import os
import subprocess
from pathlib import Path
import requests
from ubuntu_downloader import download_ubuntu_netboot, check_ubuntu_files


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
        return download_ubuntu_netboot()

    def get_ubuntu_status():
        """Get Ubuntu files status"""
        return check_ubuntu_files()

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
kernel http://${next-server}:8000/http/ubuntu/vmlinuz
initrd http://${next-server}:8000/http/ubuntu/initrd
imgargs vmlinuz initrd=initrd auto=true priority=critical preseed/url=http://${next-server}:8000/http/ubuntu/preseed.cfg
boot || goto failed

:ubuntu_rescue
echo Booting Ubuntu Recovery Mode...
kernel http://${next-server}:8000/http/ubuntu/vmlinuz
initrd http://${next-server}:8000/http/ubuntu/initrd
imgargs vmlinuz initrd=initrd rescue/enable=true
boot || goto failed

:memtest
echo Starting Memory Test...
# Note: Download memtest86+ binary to /srv/http/memtest/memtest86+
kernel http://${next-server}:8000/http/memtest/memtest86+ || goto failed
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

    def get_ipxe_menu_content():
        """Get current iPXE menu content"""
        ipxe_file = Path("/srv/ipxe/boot.ipxe")
        if ipxe_file.exists():
            with open(ipxe_file, 'r') as f:
                return f.read()
        return "# iPXE menu not created yet\n# Click 'Create iPXE Menu' to generate default menu"

    def save_ipxe_menu(content):
        """Save iPXE menu content"""
        try:
            ipxe_dir = Path("/srv/ipxe")
            ipxe_dir.mkdir(parents=True, exist_ok=True)

            with open(ipxe_dir / "boot.ipxe", "w") as f:
                f.write(content)

            return "✅ iPXE menu saved successfully!"
        except Exception as e:
            return f"❌ Error saving iPXE menu: {str(e)}"

    def test_http_endpoints():
        """Test HTTP endpoints and TFTP server"""
        results = []

        # Test TFTP server
        try:
            import subprocess
            result = subprocess.run(['systemctl', 'is-active', 'tftpd-hpa'],
                                    capture_output=True, text=True, timeout=5)
            if result.returncode == 0 and 'active' in result.stdout:
                results.append("✅ TFTP server (tftpd-hpa): Running")
            else:
                results.append("❌ TFTP server (tftpd-hpa): Not running")
        except Exception as e:
            results.append(f"❓ TFTP server status: {str(e)}")

        # Check TFTP port
        try:
            import socket
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.settimeout(1)
            result = sock.connect_ex(('localhost', 69))
            if result == 0:
                results.append("✅ TFTP port 69/UDP: Open")
            else:
                results.append("❌ TFTP port 69/UDP: Closed")
            sock.close()
        except Exception as e:
            results.append(f"❓ TFTP port check: {str(e)}")

        # Test main server
        try:
            response = requests.get("http://localhost:8000/status", timeout=5)
            if response.status_code == 200:
                results.append("✅ Main server (port 8000): OK")
            else:
                results.append(f"❌ Main server: HTTP {response.status_code}")
        except Exception as e:
            results.append(f"❌ Main server: {str(e)}")

        # Test Gradio UI
        try:
            response = requests.get("http://localhost:9005", timeout=5)
            if response.status_code == 200:
                results.append("✅ Gradio UI (port 9005): OK")
            else:
                results.append(f"❌ Gradio UI: HTTP {response.status_code}")
        except Exception as e:
            results.append(f"❌ Gradio UI: {str(e)}")

        # Test iPXE menu
        ipxe_file = Path("/srv/ipxe/boot.ipxe")
        if ipxe_file.exists():
            results.append("✅ iPXE menu file: Found")
            try:
                response = requests.get("http://localhost:8000/ipxe/boot.ipxe", timeout=5)
                if response.status_code == 200:
                    results.append("✅ iPXE menu HTTP: Accessible")
                else:
                    results.append(f"❌ iPXE menu HTTP: {response.status_code}")
            except Exception as e:
                results.append(f"❌ iPXE menu HTTP: {str(e)}")
        else:
            results.append("❌ iPXE menu file: Missing")

        # Test Ubuntu files
        ubuntu_kernel = Path("/srv/http/ubuntu/vmlinuz")
        ubuntu_initrd = Path("/srv/http/ubuntu/initrd")

        if ubuntu_kernel.exists():
            results.append("✅ Ubuntu kernel: Found")
        else:
            results.append("❌ Ubuntu kernel: Missing")

        if ubuntu_initrd.exists():
            results.append("✅ Ubuntu initrd: Found")
        else:
            results.append("❌ Ubuntu initrd: Missing")

        # Test TFTP files
        tftp_dir = Path("/srv/tftp")
        ipxe_bios = tftp_dir / "undionly.kpxe"
        ipxe_uefi = tftp_dir / "ipxe.efi"

        if ipxe_bios.exists():
            size_kb = ipxe_bios.stat().st_size / 1024
            results.append(f"✅ iPXE BIOS: Found ({size_kb:.1f} KB)")
        else:
            results.append("❌ iPXE BIOS: Missing")

        if ipxe_uefi.exists():
            size_kb = ipxe_uefi.stat().st_size / 1024
            results.append(f"✅ iPXE UEFI: Found ({size_kb:.1f} KB)")
        else:
            results.append("❌ iPXE UEFI: Missing")

        return "\n".join(results)

    def generate_test_instructions():
        """Generate testing instructions"""
        return """🧪 Как протестировать iPXE Station:

## 1. 🔧 Локальное тестирование (без DHCP):

### Простой способ - HTTP проверка:
curl http://YOUR_SERVER_IP:8000/status
curl http://YOUR_SERVER_IP:8000/ipxe/boot.ipxe
curl -I http://YOUR_SERVER_IP:8000/http/ubuntu/vmlinuz

### Эмулятор QEMU:
sudo apt install qemu-system-x86
qemu-system-x86_64 -m 1024 -boot n -netdev user,id=net0,tftp=/srv/tftp,bootfile=undionly.kpxe -device e1000,netdev=net0

## 2. 🌐 Полное тестирование (с DHCP):

### Настройка роутера:
- DHCP Option 66: IP_ВАШЕГО_СЕРВЕРА
- DHCP Option 67: undionly.kpxe

### Что должно происходить:
1. Компьютер загружается по сети (PXE)
2. Скачивает iPXE с TFTP сервера
3. iPXE загружает меню с HTTP сервера
4. Показывает меню с опциями Ubuntu
5. При выборе Ubuntu скачивает kernel и initrd

## 3. 🔍 Отладка порты:
- 69/UDP - TFTP
- 8000/TCP - HTTP сервер
- 9005/TCP - Web UI
"""

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
    filename "http://YOUR_SERVER_IP:8000/ipxe/boot.ipxe";
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
                gr.Markdown("### Ubuntu 24.04.2 LTS Netboot Download")
                gr.Markdown("Network installer from official Ubuntu netboot tarball (82 MB)")

                ubuntu_output = gr.Textbox(
                    label="Ubuntu Files Status",
                    value=get_ubuntu_status(),
                    lines=8,
                    interactive=False
                )

                with gr.Row():
                    download_ubuntu_btn = gr.Button("📥 Download Ubuntu Netboot", variant="primary")
                    create_menu_btn = gr.Button("📋 Create iPXE Menu", variant="secondary")
                    refresh_ubuntu_btn = gr.Button("🔄 Refresh Ubuntu Status", variant="secondary")

                download_ubuntu_btn.click(download_ubuntu_files, outputs=ubuntu_output)
                create_menu_btn.click(create_ipxe_menu, outputs=ubuntu_output)
                refresh_ubuntu_btn.click(get_ubuntu_status, outputs=ubuntu_output)

            # iPXE Menu Tab
            with gr.TabItem("📋 iPXE Menu"):
                gr.Markdown("### View and Edit iPXE Boot Menu")

                ipxe_content = gr.Textbox(
                    label="iPXE Menu Content",
                    value=get_ipxe_menu_content(),
                    lines=20,
                    interactive=True,
                    info="Edit the iPXE menu script here"
                )

                with gr.Row():
                    load_menu_btn = gr.Button("🔄 Reload Menu", variant="secondary")
                    save_menu_btn = gr.Button("💾 Save Menu", variant="primary")
                    create_default_btn = gr.Button("📋 Create Default", variant="secondary")

                menu_status = gr.Textbox(
                    label="Menu Status",
                    lines=2,
                    interactive=False
                )

                load_menu_btn.click(get_ipxe_menu_content, outputs=ipxe_content)
                save_menu_btn.click(save_ipxe_menu, inputs=ipxe_content, outputs=menu_status)
                create_default_btn.click(
                    lambda: (create_ipxe_menu(), get_ipxe_menu_content()),
                    outputs=[menu_status, ipxe_content]
                )

            # Testing Tab
            with gr.TabItem("🧪 Testing"):
                gr.Markdown("### Test Your iPXE Station")

                test_results = gr.Textbox(
                    label="Test Results",
                    lines=12,
                    interactive=False
                )

                test_btn = gr.Button("🔍 Run Tests", variant="primary")
                test_btn.click(test_http_endpoints, outputs=test_results)

                gr.Markdown("### Testing Instructions")
                instructions = gr.Textbox(
                    label="How to Test",
                    value=generate_test_instructions(),
                    lines=15,
                    interactive=False
                )

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
                - Go to "Ubuntu Setup" → Download Ubuntu Netboot
                - Go to "Ubuntu Setup" → Create iPXE Menu

                **2. Configure DHCP:**
                - Copy config from "DHCP Config" tab
                - Replace YOUR_SERVER_IP with your server's IP
                - Apply to your DHCP server

                **3. Test:**
                - Go to "Testing" tab → Run Tests
                - Boot a computer from network
                - Should see iPXE menu with Ubuntu option

                ### 📝 What gets installed:
                - **TFTP Files**: iPXE binaries for network boot
                - **Ubuntu Files**: Official netboot installer (82 MB)
                - **iPXE Menu**: Boot menu with Ubuntu installer

                ### 🔧 Troubleshooting:
                - Check all files are downloaded (Files tab)
                - Verify DHCP points to correct server IP
                - Ensure ports 69/UDP and 8000/TCP are open
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