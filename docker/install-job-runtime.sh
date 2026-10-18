#!/usr/bin/env bash
# Run as root during the node image build, after /usr/local Slurm is installed.
set -euo pipefail

[[ $(dpkg --print-architecture) == amd64 ]] || {
    echo 'This pinned lab runtime supports amd64 only.' >&2
    exit 1
}
[[ -f /usr/local/include/slurm/spank.h ]]

work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT
fetch() {
    local url=$1 sha=$2 output=$3
    curl --fail --location --silent --show-error "$url" --output "$output"
    printf '%s  %s\n' "$sha" "$output" | sha256sum --check --strict -
}

# Checksums: official GitHub release asset metadata and NVIDIA Packages index.
fetch 'https://github.com/NVIDIA/enroot/releases/download/v4.2.1/enroot_4.2.1-1_amd64.deb' \
    5955c51e88df0c5ed538d87abb5264609d4bad55fa8570745ed5d4ec66c8ab91 "$work/enroot.deb"
fetch 'https://nvidia.github.io/libnvidia-container/stable/deb/amd64/libnvidia-container1_1.19.1-1_amd64.deb' \
    d73bb582af893135198ef81cb22135c790a75d2ad72910446477c6c4430f3e6b "$work/libnvidia-container1.deb"
fetch 'https://nvidia.github.io/libnvidia-container/stable/deb/amd64/libnvidia-container-tools_1.19.1-1_amd64.deb' \
    5642763d51961a2295dff09990048a5dcee81edbea2a8c5084e47b09ccf17268 "$work/libnvidia-container-tools.deb"

apt-get update
DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
    "$work/enroot.deb" "$work/libnvidia-container1.deb" "$work/libnvidia-container-tools.deb" \
    squashfs-tools squashfuse fuse3 pigz zstd jq parallel bsdextrautils patch

# Pyxis v0.24.0: build against this image's exact Slurm headers, not distro Slurm.
fetch 'https://codeload.github.com/NVIDIA/pyxis/tar.gz/107519944221822ea1dace4db8e7234b2eaa4cd5' \
    32d0a56d506a3876dd59202e6a209fefae94af9803f4dd8b542e11ef2ead7907 "$work/pyxis.tar.gz"
mkdir "$work/pyxis"
tar -xzf "$work/pyxis.tar.gz" -C "$work/pyxis" --strip-components=1
CPPFLAGS=-I/usr/local/include make -C "$work/pyxis" -j2 prefix=/usr/local install

# Keep NVIDIA device injection and inherited Slurm BPF restrictions. Only the
# ldconfig selection changes so nested Docker needs no unmasked /proc mounts.
patch --batch --forward /etc/enroot/hooks.d/98-nvidia.sh /tmp/enroot-nested-ldconfig.patch
install -d -m 0755 /var/cache/enroot /var/lib/enroot /run/enroot
install -d -m 0700 -o 1000 -g 1000 \
    /var/cache/enroot/1000 /var/lib/enroot/1000 /run/enroot/1000
# /run is tmpfs at boot; recreate the private runtime directory before jobs run.
printf '%s\n' 'd /run/enroot 0755 root root -' 'd /run/enroot/1000 0700 1000 1000 -' \
    > /usr/lib/tmpfiles.d/enroot-lab.conf
rm -rf /var/lib/apt/lists/*
