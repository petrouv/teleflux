#!/bin/bash
set -euo pipefail

# Load .env file if exists
if [[ -f .env.docker ]]; then
    # shellcheck source=/dev/null
    source .env.docker
fi

# === Configuration ===
readonly REGISTRY=${DOCKER_REGISTRY:-ghcr.io}
readonly REPOSITORY=${DOCKER_REPOSITORY:-petrouv/teleflux}
readonly IMAGE_TAG=${DOCKER_TAG:-latest}
readonly PLATFORMS=("linux/amd64" "linux/arm64")
readonly NO_CACHE=${DOCKER_NO_CACHE:-false}

# Auto-detect GitHub repository if running in Git repo
if [[ -z "${GITHUB_REPOSITORY:-}" ]] && command -v git >/dev/null 2>&1; then
    if git remote get-url origin >/dev/null 2>&1; then
        GITHUB_REPOSITORY=$(git remote get-url origin | sed 's/\.git$//' | sed 's/.*github\.com[:/]/https:\/\/github.com\//')
    fi
fi

# === Functions ===

log() {
    echo "🐳 [$(date +'%H:%M:%S')] $*"
}

log_step() {
    echo ""
    echo "📦 Step $1: $2"
    echo "────────────────────────────────────────"
}

get_version() {
    if [[ -n "${VERSION:-}" ]]; then
        echo "$VERSION"
        return
    fi
    
    if [[ ! -f pyproject.toml ]]; then
        log "❌ pyproject.toml not found"
        exit 1
    fi
    
    grep '^version = ' pyproject.toml | sed 's/version = "\(.*\)"/\1/'
}

build_platform_image() {
    local platform=$1
    local tag=$2
    local arch_name
    arch_name=$(echo "$platform" | cut -d'/' -f2)
    
    log "Building $arch_name image..."
    
    local build_args=(
        --platform "$platform"
        -t "$tag"
        --push
    )
    
    if [[ "$NO_CACHE" == "true" ]]; then
        build_args+=(--no-cache)
    fi
    
    docker buildx build "${build_args[@]}" .
}


create_manifest() {
    local tag=$1
    local version=$2
    shift 2
    local arch_tags=("$@")
    
    log "Creating manifest for $tag..."
    
    local source_url="${GITHUB_REPOSITORY:-https://github.com/petrouv/teleflux}"
    local description="${DOCKER_DESCRIPTION:-Synchronize Telegram channels with Miniflux categories via RssHub}"
    local license="${DOCKER_LICENSE:-MIT}"
    local created
    created=$(date -u +%Y-%m-%dT%H:%M:%SZ)
    
    # Create temporary file with proper escaping
    local temp_script
    temp_script=$(mktemp)
    
    cat > "$temp_script" << EOF
#!/bin/bash
docker buildx imagetools create \\
    --tag "$tag" \\
    --annotation "index:org.opencontainers.image.source=$source_url" \\
    --annotation "index:org.opencontainers.image.description=$description" \\
    --annotation "index:org.opencontainers.image.licenses=$license" \\
    --annotation "index:org.opencontainers.image.version=$version" \\
    --annotation "index:org.opencontainers.image.created=$created" \\
    ${arch_tags[@]}
EOF
    
    chmod +x "$temp_script"
    "$temp_script"
    local result=$?
    rm -f "$temp_script"
    
    return $result
}

verify_manifest() {
    local tag=$1
    log "Verifying manifest: $tag"
    docker buildx imagetools inspect "$tag"
}

print_summary() {
    local version=$1
    local full_image=$2
    local latest_tag=$3
    local version_tag=$4
    local arch_tags=("${@:5}")
    
    echo ""
    echo "✅ Multi-arch image built successfully!"
    echo ""
    echo "📋 Summary:"
    echo "  Registry: $REGISTRY"
    echo "  Repository: $REPOSITORY" 
    echo "  Version: $version"
    echo "  Platforms: ${PLATFORMS[*]}"
    echo ""
    echo "🏷️  Tags created:"
    echo "  - $latest_tag"
    echo "  - $version_tag"
    for tag in "${arch_tags[@]}"; do
        echo "  - $tag"
    done
    echo ""
    echo "🔗 GitHub Container Registry:"
    echo "  https://github.com/petrouv/teleflux/pkgs/container/teleflux"
}

# === Main Script ===

main() {
    log "Starting multi-arch Docker build"
    
    # Get version
    local version
    version=$(get_version)
    log "Version: $version"
    
    # Setup image references
    local full_image="${REGISTRY}/${REPOSITORY}"
    local latest_tag="${full_image}:${IMAGE_TAG}"
    local version_tag="${full_image}:${version}"
    
    # Build architecture-specific images
    log_step "1" "Building platform images"
    
    local arch_tags=()
    for platform in "${PLATFORMS[@]}"; do
        local arch_name
        arch_name=$(echo "$platform" | cut -d'/' -f2)
        local arch_tag="${full_image}:${arch_name}-${version}"
        arch_tags+=("$arch_tag")
        
        build_platform_image "$platform" "$arch_tag"
    done
    
    # Create manifests with annotations
    log_step "2" "Creating manifests"
    
    create_manifest "$latest_tag" "$version" "${arch_tags[@]}"
    create_manifest "$version_tag" "$version" "${arch_tags[@]}"
    
    # Verify results
    log_step "3" "Verification"
    verify_manifest "$latest_tag"
    
    # Print summary
    print_summary "$version" "$full_image" "$latest_tag" "$version_tag" "${arch_tags[@]}"
}

# Run main function
main "$@" 