---
name: colima-docker
description: Expert guidance for running containers on macOS using Colima and the Docker CLI without Docker Desktop. Use this skill whenever the user asks about Colima setup, configuration, or troubleshooting; Docker CLI usage on macOS; running Docker Compose without Docker Desktop; multi-architecture container builds on Apple Silicon; managing Colima VM resources; switching Docker contexts; or any question about a daemonless/lightweight container workflow on macOS. Also trigger for questions about container networking, volume mounts, Rosetta x86 emulation, Kubernetes via Colima, or migrating from Docker Desktop to Colima.
---

# Colima + Docker CLI on macOS

This skill covers running containers on macOS using Colima as a lightweight Docker Desktop replacement. Colima spins up a Lima-backed Linux VM using Apple's native `Virtualization.framework`, exposes a Docker socket, and lets you use the standard `docker` / `docker compose` CLI as if nothing changed.

## Mental Model

```
Your Terminal (docker CLI / docker compose)
        │
        ▼
Docker socket (auto-forwarded from VM)
        │
        ▼
Lima VM — lightweight Linux (invisible day-to-day)
        │
        ▼
Docker Engine (Moby) or containerd inside the VM
        │
        ▼
Your containers
```

You never interact with the VM directly for normal work. It's just a backend.

---

## Installation

```bash
brew install colima docker docker-compose
```

> `docker` and `docker-compose` here are the CLI clients only — no daemon, no Desktop app.

Start Colima (launches the VM and Docker Engine):

```bash
colima start
```

Verify it works:

```bash
docker ps
docker run hello-world
```

---

## Common Operations

### Start / Stop

```bash
colima start          # Start with default resources
colima stop           # Stop the VM (containers are stopped)
colima status         # Check if running
colima list           # Show all named instances
```

### Custom Resources

Pass flags at start time, or set them permanently in `~/.colima/default/colima.yaml`:

```bash
colima start --cpu 4 --memory 8 --disk 60
```

| Flag | Default | Notes |
|------|---------|-------|
| `--cpu` | 2 | vCPUs |
| `--memory` | 2 | GB RAM |
| `--disk` | 60 | GB disk |
| `--runtime` | docker | `docker` or `containerd` |
| `--vm-type` | qemu | `qemu` or `vz` (macOS 13+ for `vz`) |

### Auto-start on Login

```bash
brew services start colima
```

### SSH into VM (rare)

```bash
colima ssh
```

---

## Apple Silicon (M-series) Specifics

By default Colima runs `linux/arm64`. Most modern images support ARM natively. For images that don't have ARM builds, use Rosetta emulation:

```bash
colima start --vm-type vz --vz-rosetta --arch x86_64
```

Or run a specific container with platform override:

```bash
docker run --platform linux/amd64 some-x86-only-image
```

### Multi-arch builds with buildx

```bash
docker buildx create --use
docker buildx build --platform linux/amd64,linux/arm64 -t myimage:latest .
```

---

## Multiple Named Instances

Useful for isolating projects or running separate x86/arm environments:

```bash
# Default ARM instance
colima start

# Dedicated x86 instance
colima start x86 --arch x86_64 --vm-type vz --vz-rosetta

# List instances and their Docker contexts
colima list
docker context list

# Switch between them
docker context use colima       # ARM
docker context use colima-x86   # x86
```

---

## Docker Compose

Works exactly as expected — no changes needed to your `docker-compose.yml` files:

```bash
docker compose up -d
docker compose logs -f
docker compose down
```

If using the older `docker-compose` (v1) binary:

```bash
docker-compose up -d
```

Both work with Colima.

---

## Kubernetes

Colima can run a local K3s cluster:

```bash
colima start --with-kubernetes
kubectl get nodes
```

Or enable it on an existing instance:

```bash
colima stop
colima start --with-kubernetes
```

---

## Networking

Colima containers are accessible from your Mac host at `localhost` by default for published ports:

```bash
docker run -p 8080:80 nginx
# → http://localhost:8080
```

### VPN Issues

If you use a VPN (Tailscale, Cisco Anyconnect, etc.), the VM's network may be disrupted. Workarounds:

1. Use `--vm-type vz` (macOS Virtualization framework) which handles VPN better than QEMU
2. Set a custom subnet: `colima start --network-address`
3. See `references/networking.md` for detailed VPN troubleshooting

---

## Volume Mounts

Standard bind mounts work as expected:

```bash
docker run -v $(pwd):/app node:20 npm install
```

Home directory (`~`) is automatically shared into the VM. For paths outside `~`, add them to `~/.colima/default/colima.yaml`:

```yaml
mounts:
  - location: /Volumes/external
    writable: true
```

---

## Configuration File

`~/.colima/default/colima.yaml` persists your settings so you don't need flags every time:

```yaml
cpu: 4
memory: 8
disk: 60
vmType: vz
rosetta: true
runtime: docker
kubernetes:
  enabled: false
```

After editing, restart Colima: `colima stop && colima start`

---

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| `Cannot connect to Docker daemon` | Run `colima start` — the VM isn't running |
| `docker: context not found` | Run `colima start` to recreate the context |
| Slow file I/O on volumes | Use `--vm-type vz` for better VirtioFS performance |
| x86 image fails on M-series | Add `--platform linux/amd64` or start an x86 Colima instance |
| Containers unreachable from host | Check port is published with `-p`; check VPN isn't blocking |
| High CPU when idle | Upgrade to `--vm-type vz`; QEMU has higher idle overhead |
| Out of disk space in VM | `colima stop && colima delete && colima start --disk 100` |

For deeper troubleshooting, see `references/troubleshooting.md`.

---

## Migration from Docker Desktop

1. Quit Docker Desktop
2. `brew install colima docker docker-compose`
3. `colima start`
4. All existing images, volumes, and compose files work without changes

> Docker Desktop and Colima can coexist but will fight over the `docker` context. Uninstalling Docker Desktop is recommended once you've verified Colima works.

---

## Reference Files

- `references/networking.md` — VPN issues, custom DNS, host-to-container routing
- `references/troubleshooting.md` — Common errors with detailed fixes
- `references/colima-yaml.md` — Full annotated `colima.yaml` reference
