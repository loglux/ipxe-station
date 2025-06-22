#!/bin/bash
# iPXE Station - Smart Deploy Script
# Universal deployment script for Docker environments

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

# Print colored output
print_header() {
    echo -e "${BLUE}🌐 iPXE Station - Smart Deploy${NC}"
    echo "========================================"
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

# Stop and remove existing container

# Stop and remove existing container - ПРИНУДИТЕЛЬНО
cleanup_existing() {
    print_info "Cleaning up existing containers..."

    # Force stop and remove container if exists (без проверок!)
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
    print_info "Building Docker image..."

    if ! docker build -t ${IMAGE_NAME} .; then
        print_error "Failed to build Docker image"
        exit 1
    fi

    print_success "Docker image built successfully"
}

# Run container
run_container() {
    print_info "Starting iPXE Station container..."

    # Run container with port mapping
    if ! docker run -d \
        --name ${CONTAINER_NAME} \
        -p ${EXTERNAL_PORT}:${INTERNAL_PORT} \
        -p ${TFTP_PORT}:${TFTP_PORT}/udp \
        --restart unless-stopped \
        ${IMAGE_NAME}; then
        print_error "Failed to start container"
        exit 1
    fi

    print_success "Container started successfully"
}

# Wait for service to be ready
wait_for_service() {
    print_info "Waiting for service to be ready..."

    local max_attempts=30
    local attempt=1

    while [ $attempt -le $max_attempts ]; do
        if command_exists curl; then
            # Проверяем главную страницу вместо /api/ping
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
    print_success "iPXE Station deployed successfully!"
    echo
    echo "🌐 Application URLs:"
    echo "  • Main page:  http://localhost:${EXTERNAL_PORT}/"
    echo "  • Web UI:     http://localhost:${EXTERNAL_PORT}/gradio"
    echo "  • Status:     http://localhost:${EXTERNAL_PORT}/status"
    echo "  • TFTP:       localhost:${TFTP_PORT}/UDP"
    echo
    echo "📋 Container management:"
    echo "  • View logs:  docker logs -f ${CONTAINER_NAME}"
    echo "  • Stop:       docker stop ${CONTAINER_NAME}"
    echo "  • Start:      docker start ${CONTAINER_NAME}"
    echo "  • Remove:     docker rm -f ${CONTAINER_NAME}"
    echo "  • Redeploy:   ./deploy.sh"
    echo
    print_info "Container status:"
    docker ps --filter "name=${CONTAINER_NAME}" --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"
}


# Main deployment function
deploy() {
    print_header

    # Prerequisites checks
    check_docker
    check_requirements
    check_ports

    # Cleanup and deploy
    cleanup_existing
    build_image
    run_container

    # Post-deployment
    wait_for_service
    show_results
}

# Help function
show_help() {
    echo "iPXE Station Deploy Script"
    echo
    echo "Usage: $0 [command]"
    echo
    echo "Commands:"
    echo "  deploy     Deploy iPXE Station (default)"
    echo "  stop       Stop iPXE Station"
    echo "  start      Start iPXE Station"
    echo "  restart    Restart iPXE Station"
    echo "  logs       Show container logs"
    echo "  status     Show container status"
    echo "  remove     Remove iPXE Station container"
    echo "  help       Show this help"
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
        print_warning "Removing iPXE Station container..."
        docker rm -f ${CONTAINER_NAME} 2>/dev/null && print_success "Container removed" || print_warning "Container not found"
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