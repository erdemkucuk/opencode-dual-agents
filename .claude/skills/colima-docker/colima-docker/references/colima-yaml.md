# colima.yaml Full Reference

Location: `~/.colima/default/colima.yaml`
For named instances: `~/.colima/<name>/colima.yaml`

After editing, apply changes with: `colima stop && colima start`

---

## Annotated Example

```yaml
# Number of vCPUs allocated to the VM
# Default: 2
cpu: 4

# RAM in GB
# Default: 2
memory: 8

# Disk size in GB — cannot be resized after creation without deleting the VM
# Default: 60
disk: 60

# Container runtime: "docker" or "containerd"
# Use "docker" unless you specifically need nerdctl/containerd-native workflows
# Default: docker
runtime: docker

# VM type: "qemu" or "vz"
# "vz" = Apple Virtualization.framework (macOS 13+ required)
# "vz" is recommended: faster I/O, better VPN compat, lower idle CPU
# Default: qemu
vmType: vz

# Enable Rosetta x86 emulation (requires vmType: vz)
# Allows running linux/amd64 images on Apple Silicon
# Default: false
rosetta: true

# CPU architecture: "host", "x86_64", "aarch64"
# Default: host (matches your Mac's CPU)
arch: host

# Mount additional host directories into the VM
# Home directory (~) is always mounted automatically
mounts:
  - location: /Volumes/external-drive
    writable: true
  - location: /opt/myproject
    writable: false

# SSH port for `colima ssh` (auto-assigned by default)
# sshPort: 0

# Kubernetes (K3s) configuration
kubernetes:
  enabled: false
  # K3s version — leave empty for latest
  # version: v1.28.3+k3s1
  # K3s install args
  # k3sArgs: []

# DNS servers for the VM
# Useful if VPN is overriding DNS or you need internal resolvers
dns:
  - 8.8.8.8
  - 1.1.1.1

# Static DNS host entries (like /etc/hosts inside the VM)
dnsHosts:
  # myservice.internal: 192.168.1.50

# Network: enable host network address assignment
# Helps with VPN compatibility
network:
  address: false

# Docker daemon configuration passed directly to dockerd
# Same options as /etc/docker/daemon.json
dockerDaemon:
  # Example: add insecure registries
  # insecure-registries:
  #   - myregistry.local:5000
  #
  # Example: custom data root
  # data-root: /data/docker
  #
  # Example: log driver
  # log-driver: json-file
  # log-opts:
  #   max-size: "10m"
  #   max-file: "3"

# Provision scripts run inside the VM on first start
# Useful for installing extra tools into the VM
provision:
  # - mode: system   # run as root
  #   script: |
  #     apt-get install -y htop
  # - mode: user     # run as the colima user
  #   script: |
  #     echo "VM ready"

# Environment variables injected into the VM
env: {}
  # MY_VAR: my_value
```

---

## Common Presets

### Minimal (low-resource laptop)
```yaml
cpu: 2
memory: 4
disk: 40
vmType: vz
runtime: docker
```

### High-performance dev machine
```yaml
cpu: 8
memory: 16
disk: 100
vmType: vz
rosetta: true
runtime: docker
```

### Kubernetes development
```yaml
cpu: 4
memory: 8
disk: 80
vmType: vz
runtime: docker
kubernetes:
  enabled: true
```

### x86 compatibility (Apple Silicon)
```yaml
cpu: 4
memory: 8
disk: 60
vmType: vz
rosetta: true
arch: x86_64
runtime: docker
```
