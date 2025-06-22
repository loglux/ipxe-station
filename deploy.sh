#!/bin/bash
# iPXE Station - Smart Deploy Script with Volume Support
# Universal deployment script for Docker environments with persistent storage

set -e  # Exit on any error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
CONTAINER_NAME="ipxe-station"
IMAGE_NAME="ipxe-station"
EXTERNAL_PORT="9005"
INTERNAL_PORT="8000"
TFTP_PORT="69"

# Volume configuration
DATA_DIR="./data"
VOLUMES_TFTP="${DATA_DIR}/srv/tftp"
VOLUMES_HTTP="${DATA_DIR}/srv/http"
VOLUMES_IPXE="${DATA_DIR}/srv/ipxe"
VOLUMES_DHCP="${DATA_DIR}/srv/dhcp"

# Print colored output
print_header() {
    echo -e "${BLUE}🌐 iPXE Station - Smart Deploy with Volumes${NC}"
    echo "=================================================="
}

print_success() {
    echo -e "${GREEN}✅ $1${NC}"
}

print_error() {
    echo -e "${RED}❌ $1${NC}"
}

print_warning() {
    echo -e "${YELLOW}⚠️  $1${NC}"
}

print_info() {
    echo -e "${BLUE}ℹ️  $1${NC}"
}

# Check if command exists
command_exists() {
    command -v "$1" >/dev/null 2>&1
}

# Check Docker installation
check_docker() {
    print_info "Checking Docker installation..."

    if ! command_exists docker; then
        print_error "Docker not found. Please install Docker first."
        echo "Visit: https://docs.docker.com/get-docker/"
        exit 1
    fi

    print_success "Docker found"
}

# Check if port is available
check_port() {
    local port=$1
    local protocol=${2:-tcp}

    if command_exists netstat; then
        if netstat -ln 2>/dev/null | grep -q ":${port} "; then
            return 1  # Port is in use
        fi
    elif command_exists ss; then
        if ss -ln 2>/dev/null | grep -q ":${port} "; then
            return 1  # Port is in use
        fi
    fi
    return 0  # Port is available
}

# Create host directories for volumes
create_host_directories() {
    print_info "Creating host directories for persistent storage..."

    # Create main data directory
    mkdir -p "${DATA_DIR}"
    print_success "Created data directory: ${DATA_DIR}"

    # Create volume directories
    local dirs=("${VOLUMES_TFTP}" "${VOLUMES_HTTP}" "${VOLUMES_IPXE}" "${VOLUMES_DHCP}")

    for dir in "${dirs[@]}"; do
        if [ ! -d "$dir" ]; then
            mkdir -p "$dir"
            print_success "Created volume directory: $dir"
        else
            print_info "Volume directory exists: $dir"
        fi
    done

    # Set proper permissions
    chmod -R 755 "${DATA_DIR}"
    print_success "Set proper permissions on ${DATA_DIR}"

    # Create subdirectories for organization
    mkdir -p "${VOLUMES_HTTP}/iso"
    mkdir -p "${VOLUMES_HTTP}/custom"

    # Show disk space information
    print_info "Disk space available:"
    df -h "${DATA_DIR}" | tail -1 | awk '{print "  Available: " $4 " on " $6}'
}

# Stop and remove existing container - FORCEFULLY
cleanup_existing() {
    print_info "Cleaning up existing containers..."

    # Force stop and remove container if exists (without checks!)
    print_info "Force stopping any existing '${CONTAINER_NAME}' container..."
    docker stop ${CONTAINER_NAME} >/dev/null 2>&1 || true

    print_info "Force removing any existing '${CONTAINER_NAME}' container..."
    docker rm -f ${CONTAINER_NAME} >/dev/null 2>&1 || true

    print_success "Cleanup completed"

    # Remove old image to force rebuild
    print_info "Removing old Docker image..."
    docker rmi ${IMAGE_NAME} >/dev/null 2>&1 || true
    print_success "Old image removed"

    # Clean up unused Docker resources
    print_info "Cleaning up Docker system..."
    docker system prune -f >/dev/null 2>&1 || true
    print_success "Docker cleanup completed"
}

# Check required files
check_requirements() {
    print_info "Checking project requirements..."

    local required_files=("Dockerfile" "requirements.txt" "app/main.py" "app/gradio_ui.py")

    for file in "${required_files[@]}"; do
        if [ ! -f "$file" ]; then
            print_error "Required file not found: $file"
            exit 1
        fi
    done

    # Check for script files
    local script_files=("scripts/setup-volumes.sh" "scripts/start.sh")
    for file in "${script_files[@]}"; do
        if [ ! -f "$file" ]; then
            print_error "Required script file not found: $file"
            print_info "Please create the scripts directory and files"
            exit 1
        fi
    done

    print_success "All required files found"
}

# Check port availability
check_ports() {
    print_info "Checking port availability..."

    if ! check_port ${EXTERNAL_PORT}; then
        print_error "Port ${EXTERNAL_PORT} is already in use"
        print_info "Please change EXTERNAL_PORT in the script or stop the service using this port"
        exit 1
    fi
    print_success "Port ${EXTERNAL_PORT} is available"

    # Check TFTP port (might be in use by system)
    if ! check_port ${TFTP_PORT} udp; then
        print_warning "TFTP port ${TFTP_PORT}/UDP might be in use"
        print_info "The container will still start, but TFTP might not work"
    else
        print_success "TFTP port ${TFTP_PORT}/UDP is available"
    fi
}

# Build Docker image
build_image() {
    print_info "Building Docker image with volume support..."

    if ! docker build -t ${IMAGE_NAME} .; then
        print_error "Failed to build Docker image"
        exit 1
    fi

    print_success "Docker image built successfully"
}

# Run container with volumes
run_container() {
    print_info "Starting iPXE Station container with persistent volumes..."

    # Prepare absolute paths for volumes
    local abs_data_dir=$(cd "${DATA_DIR}" && pwd)

    # Run container with volume mounts
    if ! docker run -d \
        --name ${CONTAINER_NAME} \
        -p ${EXTERNAL_PORT}:${INTERNAL_PORT} \
        -p ${TFTP_PORT}:${TFTP_PORT}/udp \
        -v "${abs_data_dir}/srv/tftp:/srv/tftp" \
        -v "${abs_data_dir}/srv/http:/srv/http" \
        -v "${abs_data_dir}/srv/ipxe:/srv/ipxe" \
        -v "${abs_data_dir}/srv/dhcp:/srv/dhcp" \
        --restart unless-stopped \
        ${IMAGE_NAME}; then
        print_error "Failed to start container"
        exit 1
    fi

    print_success "Container started successfully with volumes"
    print_info "Volume mappings:"
    echo "  📁 TFTP:  ${abs_data_dir}/srv/tftp  → /srv/tftp"
    echo "  📁 HTTP:  ${abs_data_dir}/srv/http  → /srv/http"
    echo "  📁 iPXE:  ${abs_data_dir}/srv/ipxe  → /srv/ipxe"
    echo "  📁 DHCP:  ${abs_data_dir}/srv/dhcp  → /srv/dhcp"
}

# Wait for service to be ready
wait_for_service() {
    print_info "Waiting for service to be ready..."

    local max_attempts=30
    local attempt=1

    while [ $attempt -le $max_attempts ]; do
        if command_exists curl; then
            # Check main page instead of /api/ping
            if curl -s http://localhost:${EXTERNAL_PORT}/ >/dev/null 2>&1; then
                break
            fi
        elif command_exists wget; then
            if wget -q --spider http://localhost:${EXTERNAL_PORT}/ >/dev/null 2>&1; then
                break
            fi
        else
            # Fallback: just check if container is running
            if docker ps --format "table {{.Names}}" | grep -q "^${CONTAINER_NAME}$"; then
                break
            fi
        fi

        if [ $attempt -eq $max_attempts ]; then
            print_warning "Service might not be ready yet"
            break
        fi

        sleep 2
        attempt=$((attempt + 1))
    done
}

# Show deployment results
show_results() {
    print_success "iPXE Station deployed successfully with persistent storage!"
    echo
    echo "🌐 Application URLs:"
    echo "  • Main page:  http://localhost:${EXTERNAL_PORT}/"
    echo "  • Web UI:     http://localhost:${EXTERNAL_PORT}/gradio"
    echo "  • Status:     http://localhost:${EXTERNAL_PORT}/status"
    echo "  • TFTP:       localhost:${TFTP_PORT}/UDP"
    echo
    echo "📁 Persistent Storage:"
    local abs_data_dir=$(cd "${DATA_DIR}" && pwd)
    echo "  • Data directory: ${abs_data_dir}"
    echo "  • TFTP files:     ${abs_data_dir}/srv/tftp/"
    echo "  • HTTP files:     ${abs_data_dir}/srv/http/"
    echo "  • iPXE scripts:   ${abs_data_dir}/srv/ipxe/"
    echo "  • DHCP configs:   ${abs_data_dir}/srv/dhcp/"
    echo
    echo "💾 Storage Benefits:"
    echo "  • Ubuntu versions persist across container restarts"
    echo "  • Large files don't increase container size"
    echo "  • Easy backup and migration"
    echo "  • Multiple versions supported simultaneously"
    echo
    echo "📋 Container management:"
    echo "  • View logs:  docker logs -f ${CONTAINER_NAME}"
    echo "  • Stop:       docker stop ${CONTAINER_NAME}"
    echo "  • Start:      docker start ${CONTAINER_NAME}"
    echo "  • Remove:     docker rm -f ${CONTAINER_NAME}"
    echo "  • Redeploy:   ./deploy.sh"
    echo "  • Data backup: tar -czf ipxe-backup.tar.gz ${DATA_DIR}"
    echo
    print_info "Container status:"
    docker ps --filter "name=${CONTAINER_NAME}" --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"

    echo
    print_info "Volume usage:"
    docker exec ${CONTAINER_NAME} df -h /srv/ 2>/dev/null | grep -E "(Filesystem|/srv)" || echo "Volume info will be available after first use"
}

# Show volume information
show_volume_info() {
    print_info "Volume information:"
    local abs_data_dir=$(cd "${DATA_DIR}" && pwd)

    echo "📊 Storage usage:"
    du -sh "${abs_data_dir}" 2>/dev/null || echo "Data directory: ${abs_data_dir}"

    if [ -d "${VOLUMES_HTTP}" ]; then
        echo "🐧 Ubuntu versions:"
        find "${VOLUMES_HTTP}" -maxdepth 1 -name "ubuntu-*" -type d 2>/dev/null | \
            sed 's|.*/ubuntu-|  • Ubuntu |' | sort || echo "  • No Ubuntu versions installed yet"
    fi

    echo "📁 Directory structure:"
    tree "${DATA_DIR}" -L 3 2>/dev/null || ls -la "${DATA_DIR}"
}

# Backup data
backup_data() {
    local backup_name="ipxe-backup-$(date +%Y%m%d-%H%M%S).tar.gz"
    print_info "Creating backup: ${backup_name}"

    if [ -d "${DATA_DIR}" ]; then
        tar -czf "${backup_name}" "${DATA_DIR}"
        print_success "Backup created: ${backup_name}"
        ls -lh "${backup_name}"
    else
        print_warning "No data directory found to backup"
    fi
}

# Restore data from backup
restore_data() {
    local backup_file="$1"

    if [ -z "$backup_file" ]; then
        print_error "Please specify backup file: $0 restore <backup_file>"
        exit 1
    fi

    if [ ! -f "$backup_file" ]; then
        print_error "Backup file not found: $backup_file"
        exit 1
    fi

    print_warning "This will overwrite existing data in ${DATA_DIR}"
    read -p "Continue? (y/N): " confirm

    if [[ $confirm == [yY] ]]; then
        print_info "Restoring from: $backup_file"
        tar -xzf "$backup_file"
        print_success "Restore completed"
    else
        print_info "Restore cancelled"
    fi
}

# Main deployment function
deploy() {
    print_header

    # Prerequisites checks
    check_docker
    check_requirements

    # ⚡ CLEANUP FIRST - before checking ports!
    cleanup_existing

    # Create host directories for volumes
    create_host_directories

    # Now check ports (after cleanup)
    check_ports

    # Deploy
    build_image
    run_container

    # Post-deployment
    wait_for_service
    show_results
}

# Help function
show_help() {
    echo "iPXE Station Deploy Script with Volume Support"
    echo
    echo "Usage: $0 [command]"
    echo
    echo "Commands:"
    echo "  deploy     Deploy iPXE Station with volumes (default)"
    echo "  stop       Stop iPXE Station"
    echo "  start      Start iPXE Station"
    echo "  restart    Restart iPXE Station"
    echo "  logs       Show container logs"
    echo "  status     Show container status"
    echo "  remove     Remove iPXE Station container (keeps data)"
    echo "  info       Show volume and storage information"
    echo "  backup     Create backup of all data"
    echo "  restore    Restore data from backup"
    echo "  help       Show this help"
    echo
    echo "Volume Information:"
    echo "  Data directory: ${DATA_DIR}"
    echo "  TFTP files:     ${VOLUMES_TFTP}"
    echo "  HTTP files:     ${VOLUMES_HTTP}"
    echo "  iPXE scripts:   ${VOLUMES_IPXE}"
    echo "  DHCP configs:   ${VOLUMES_DHCP}"
}

# Command handling
case "${1:-deploy}" in
    deploy)
        deploy
        ;;
    stop)
        print_info "Stopping iPXE Station..."
        docker stop ${CONTAINER_NAME} 2>/dev/null && print_success "Container stopped" || print_warning "Container not running"
        ;;
    start)
        print_info "Starting iPXE Station..."
        docker start ${CONTAINER_NAME} 2>/dev/null && print_success "Container started" || print_error "Failed to start container"
        ;;
    restart)
        print_info "Restarting iPXE Station..."
        docker restart ${CONTAINER_NAME} 2>/dev/null && print_success "Container restarted" || print_error "Failed to restart container"
        ;;
    logs)
        docker logs -f ${CONTAINER_NAME}
        ;;
    status)
        docker ps --filter "name=${CONTAINER_NAME}" --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"
        ;;
    remove)
        print_warning "Removing iPXE Station container (data will be preserved)..."
        docker rm -f ${CONTAINER_NAME} 2>/dev/null && print_success "Container removed" || print_warning "Container not found"
        print_info "Data preserved in: ${DATA_DIR}"
        ;;
    info)
        show_volume_info
        ;;
    backup)
        backup_data
        ;;
    restore)
        restore_data "$2"
        ;;
    help|--help|-h)
        show_help
        ;;
    *)
        print_error "Unknown command: $1"
        show_help
        exit 1
        ;;
esac