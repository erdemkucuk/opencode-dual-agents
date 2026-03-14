# Colima Troubleshooting Reference

## Cannot connect to Docker daemon

**Error:** `Cannot connect to the Docker daemon at unix:///var/run/docker.sock`

**Causes & fixes:**

1. Colima isn't running → `colima start`
2. Wrong Docker context active:
   ```bash
   docker context list
   docker context use colima
   ```
3. Docker Desktop is fighting for the socket:
   ```bash
   # Quit Docker Desktop, then:
   colima stop && colima start
   ```

---

## Context disappeared after reboot

Colima contexts are recreated on each `colima start`. If you're using `brew services start colima` for auto-start, the context should persist. If not:

```bash
colima start
docker context use colima
```

Make `colima` the default context permanently:

```bash
docker context use colima
```

---

## Slow volume mount performance

Symptoms: `npm install`, `composer install`, or file-watching is very slow.

**Fix: Switch to vz + VirtioFS**

```bash
colima stop
colima delete
colima start --vm-type vz
```

VirtioFS (used with `vz`) is significantly faster than the QEMU default for file I/O-heavy workloads.

**Alternative: Use named volumes instead of bind mounts**

Named volumes live inside the VM and bypass the host filesystem sync entirely:

```yaml
# docker-compose.yml
volumes:
  node_modules:

services:
  app:
    volumes:
      - .:/app
      - node_modules:/app/node_modules  # keeps node_modules inside VM
```

---

## x86 image fails on Apple Silicon

**Error:** `exec /usr/local/bin/docker-entrypoint.sh: exec format error`

The image has no `linux/arm64` variant. Solutions:

1. **Run with Rosetta emulation (recommended):**
   ```bash
   colima stop
   colima delete
   colima start --vm-type vz --vz-rosetta
   docker run --platform linux/amd64 <image>
   ```

2. **Start a dedicated x86 instance:**
   ```bash
   colima start x86 --arch x86_64 --vm-type vz --vz-rosetta
   docker context use colima-x86
   docker run <image>
   ```

---

## Out of disk space inside VM

**Error:** `no space left on device`

```bash
# Check VM disk usage
colima ssh -- df -h

# Option 1: Delete and recreate with more disk
colima stop
colima delete   # WARNING: destroys all images/volumes
colima start --disk 100

# Option 2: Prune unused Docker data first
docker system prune -af --volumes
```

> There is currently no way to resize an existing Colima VM disk. Delete + recreate is required.

---

## High CPU usage when idle

QEMU VM type has higher idle CPU overhead. Switch to Apple's Virtualization framework:

```bash
colima stop
colima delete
colima start --vm-type vz
```

---

## Colima won't start / hangs on startup

```bash
# Check logs
colima start --verbose

# Or inspect Lima logs
cat ~/.lima/colima/serial.log | tail -50

# Nuclear option: delete and recreate
colima delete
colima start
```

---

## Docker Compose: "service failed to build"

Usually a platform mismatch or missing buildx:

```bash
# Ensure buildx is set up
docker buildx install

# Force build for current platform
docker compose build --platform linux/arm64

# Or add to docker-compose.yml
# platform: linux/arm64
```

---

## Port already in use

```bash
# Find what's using the port on your Mac
lsof -i :8080

# Or check if another container has it
docker ps | grep 8080
```

---

## Colima and Lima version mismatch

After a `brew upgrade`, Colima and Lima may be incompatible:

```bash
brew upgrade colima lima
colima stop
colima delete
colima start
```

---

## Docker credentials / registry login not persisting

By default, Docker credential helpers may not be configured for the Colima context. Add to `~/.docker/config.json`:

```json
{
  "credsStore": "osxkeychain"
}
```

Or use `docker login` and it will store credentials in the file directly (less secure but functional).

---

## Useful Diagnostic Commands

```bash
# Colima status and version
colima version
colima status

# Lima VM info
limactl list

# Docker system info (includes runtime, storage driver)
docker info

# Check Docker context
docker context inspect colima

# VM disk / memory / CPU
colima ssh -- free -h
colima ssh -- df -h
colima ssh -- nproc

# Tail VM serial log (for boot issues)
tail -f ~/.lima/colima/serial.log
```
