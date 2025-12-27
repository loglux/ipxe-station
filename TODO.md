# TODO - Future Improvements

This document tracks missing features and potential improvements for future development.

## Missing Features

### High Priority

#### 1. Backup/Restore System for Menus
- **Description**: Allow users to backup and restore menu configurations
- **Implementation**:
  - Export menu.json to downloadable backup file
  - Import/restore menu.json from backup
  - Version metadata (timestamp, description)
  - Validation before restore
- **Use case**: Protect against accidental menu corruption, test configurations safely

#### 2. Download Resumption for Large ISOs
- **Description**: Resume interrupted downloads instead of starting over
- **Current state**: Downloads restart from 0% if interrupted
- **Implementation**:
  - HTTP Range requests support
  - Track download progress to disk
  - Verify partial downloads with checksums
  - Resume from last checkpoint
- **Use case**: Large Ubuntu ISOs (4-6GB) on unstable connections

#### 3. Upload Validation and Virus Scanning
- **Description**: Validate and scan uploaded ISO files
- **Current state**: No validation of uploaded files
- **Implementation**:
  - File type validation (magic bytes, not just extension)
  - Size limits and quotas
  - Optional ClamAV integration for virus scanning
  - Checksum verification against known good hashes
- **Use case**: Prevent upload of malicious or corrupted files

### Medium Priority

#### 4. Transaction Support for Menu Changes
- **Description**: Atomic menu updates with rollback capability
- **Current state**: Menu changes are immediate, no undo
- **Implementation**:
  - Staging area for menu changes
  - Preview before commit
  - Rollback to previous version
  - Change history/audit log
- **Use case**: Safe menu editing, especially for production environments

#### 5. DHCP Configuration Validation
- **Description**: Validate DHCP settings without requiring root privileges
- **Current state**: Validation requires network interface access
- **Implementation**:
  - Syntax-only validation mode
  - Network simulation/dry-run
  - Warning messages about privilege requirements
  - Documentation for proper setup
- **Use case**: Users in Docker/restricted environments

#### 6. Frontend API Retry Logic
- **Description**: Automatic retry for failed API requests
- **Current state**: API failures require manual page refresh
- **Implementation**:
  - Exponential backoff retry utility
  - Retry only on transient errors (5xx, timeouts)
  - User notification of retry attempts
  - Max retry limit to prevent infinite loops
- **Use case**: Improved resilience in unstable network conditions
- **Note**: Low priority for local Docker deployments

### Low Priority

#### 7. Advanced Pagination for Large File Lists
- **Description**: Full pagination with search/filter for asset listings
- **Current state**: Simple slice(0, 20) for HTTP assets
- **Implementation**:
  - Pagination controls (prev/next, page numbers)
  - Search/filter by filename
  - Sort by name/size/date
  - Configurable page size
- **Use case**: Servers with hundreds of boot assets
- **Note**: Current simple approach works for typical use cases

#### 8. Menu Entry Templates
- **Description**: Predefined templates for common boot scenarios
- **Current state**: Wizard has some templates, but limited
- **Implementation**:
  - Template library (Ubuntu desktop/server, Debian, rescue tools)
  - Template customization before adding
  - User-defined templates (save current entry as template)
  - Template sharing/import
- **Use case**: Faster menu creation for common distributions

#### 9. Multi-architecture Support Indicators
- **Description**: Visual indicators for architecture-specific entries
- **Current state**: No visual distinction for x86_64/ARM/UEFI/BIOS entries
- **Implementation**:
  - Architecture badges in menu builder
  - Filter by architecture
  - Conditional logic helpers (architecture detection)
  - Architecture compatibility warnings
- **Use case**: Complex environments with mixed architectures

#### 10. Real-time Boot Monitoring
- **Description**: Monitor active PXE boot sessions in real-time
- **Current state**: Only historical logs available
- **Implementation**:
  - TFTP/HTTP access log parsing
  - Live dashboard of active boots
  - Boot success/failure tracking
  - Client MAC/IP identification
- **Use case**: Troubleshooting boot issues, monitoring lab deployments

## Completed Improvements

### Security Fixes ✅
- [x] iPXE injection vulnerabilities (echo text escaping)
- [x] GRUB injection vulnerabilities (single-quote escaping)
- [x] Path traversal in ISO manager
- [x] Path traversal in file serving endpoints (/ipxe, /tftp)

### Functional Fixes ✅
- [x] Pydantic v2 migration (.dict() → .model_dump())
- [x] Port configuration consistency (8000 → 9021)
- [x] Race conditions in download progress tracking
- [x] Download timeout for large ISOs (60s → 600s read timeout)
- [x] Silent exception handlers (added proper logging)
- [x] Hardcoded IP addresses (moved to environment variables)
- [x] Input sanitization in menu parsing (bounds checking)

### Code Quality ✅
- [x] Removed orphaned Gradio UI code (ipxe_menu directory)
- [x] Removed obsolete fastapi_main.py entry point
- [x] Console logging cleanup (removed debug logs, kept error/warn)

## Notes

- This is a living document - add new ideas as they come up
- Prioritise based on actual user needs, not hypothetical scenarios
- Consider backwards compatibility for all changes
- Follow CLAUDE.md guidelines for all implementations
