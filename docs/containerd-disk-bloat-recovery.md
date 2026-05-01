# Containerd Disk Bloat Recovery (DigitalOcean Droplet)

## Issue

Droplet disk repeatedly hit `100%` usage even after Docker prune commands.

## Symptoms

- `df -h` showed root filesystem full (`/dev/vda4` at 99-100%).
- `docker system df -v` showed relatively small image/container usage.
- `du -xhd1 /var/lib` showed `containerd` consuming tens of GB.

## Root Cause

Disk growth was in `containerd` state under `/var/lib/containerd`, not in normal Docker image/container objects tracked by `docker system prune`.

## Working Fix

Run as `root`:

```bash
systemctl stop containerd
rm -rf /var/lib/containerd/*
systemctl start containerd
df -h
```

This reclaimed the blocked disk space and restored normal operation.

## Verification

After cleanup:

- `df -h` should show significant free space on `/`.
- `du -xhd1 /var/lib | sort -h` should show much smaller `/var/lib/containerd`.

## Safety Notes

- This is a destructive reset of containerd state. Only use when that runtime data is safe to discard.
- If running Kubernetes/k3s workloads, prefer runtime-aware cleanup (`crictl`/`ctr`) before full deletion.
- Keep a backup/snapshot if workloads are stateful.

## Prevention

- Periodically check disk:
  - `df -h`
  - `du -xhd1 /var/lib | sort -h`
- Keep Docker build context small with a correct `.dockerignore`.
- Prune build cache regularly if image builds are frequent.
