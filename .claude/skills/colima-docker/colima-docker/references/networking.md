# Colima Networking Reference

## Default Behavior

- Containers publish ports to `localhost` on the Mac host
- The VM gets a private IP (usually `192.168.5.x`)
- DNS resolution inside containers works out of the box
- Inter-container networking via Docker networks works normally

## Accessing Containers from Host

```bash
# Standard port publishing
docker run -p 8080:80 nginx
curl http://localhost:8080

# Expose on all interfaces (useful for mobile testing on same network)
docker run -p 0.0.0.0:8080:80 nginx
```

## VPN Compatibility

VPNs (Tailscale, Cisco AnyConnect, Mullvad, etc.) commonly break Colima networking by hijacking the VM's default route or conflicting with subnet ranges.

### Fix 1: Switch to vz VM type (recommended)

macOS Virtualization framework handles VPN routing better than QEMU:

```bash
colima stop
colima delete
colima start --vm-type vz
```

### Fix 2: Custom network address

Avoids subnet conflicts with VPN-assigned ranges:

```bash
colima start --network-address
```

Or in `colima.yaml`:
```yaml
network:
  address: true
```

### Fix 3: Tailscale-specific

Tailscale and Colima can conflict. Add Colima's subnet to Tailscale's split tunnel:

```bash
# Find Colima's subnet
colima ssh -- ip route

# Add to Tailscale exclusions via the Tailscale app preferences
```

### Fix 4: DNS override inside containers

If containers can't resolve external DNS while VPN is active:

```bash
# In docker-compose.yml
services:
  app:
    dns:
      - 8.8.8.8
      - 1.1.1.1
```

Or globally in `/etc/docker/daemon.json` (inside the VM):

```bash
colima ssh
sudo sh -c 'echo "{\"dns\": [\"8.8.8.8\"]}" > /etc/docker/daemon.json'
sudo systemctl restart docker
exit
```

## Host-to-Container Direct Access (no port publishing)

The VM has a fixed IP you can route to directly:

```bash
# Get the VM IP
colima ssh -- hostname -I

# Or
docker inspect <container> | grep IPAddress
```

Note: This IP is only reachable while Colima is running and may change between restarts.

## Container-to-Host Communication

From inside a container, reach the Mac host at:

```
host.docker.internal
```

This resolves to the VM gateway (which NATs to your Mac). Standard Docker behavior.

## Custom DNS

To add custom DNS or search domains to the VM:

```yaml
# ~/.colima/default/colima.yaml
dns:
  - 192.168.1.1
  - 8.8.8.8
dnsHosts:
  myservice.local: 192.168.1.100
```

## Docker Networks

Standard Docker networking works as expected:

```bash
# Create a named network
docker network create mynet

# Connect containers
docker run --network mynet --name db postgres
docker run --network mynet myapp  # can reach 'db' by hostname
```

## Exposing to LAN (other devices on your network)

By default containers are only reachable from your Mac. To expose to LAN:

```bash
# Get your Mac's LAN IP
ipconfig getifaddr en0

# Publish on all interfaces
docker run -p 0.0.0.0:8080:80 nginx

# Now reachable at http://<your-mac-ip>:8080 from other devices
```
