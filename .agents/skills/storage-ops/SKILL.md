---
name: storage-ops
description: >-
  Standardized workstation and server storage triage, bounded depth disk inspection,
  pacman cache hygiene, journal vacuuming, Docker prune, Btrfs/Timeshift snapshot inspection,
  and modern ntfs3 mount runbook. Use when triaging disk space exhaustion, cleaning pacman caches,
  vacuuming systemd journal logs, pruning Docker assets, managing Btrfs/Timeshift subvolumes,
  or mounting NTFS drives with in-kernel ntfs3.
---
<!-- SPDX-License-Identifier: Apache-2.0 -->
<!-- Copyright (c) 2026 Arafat Zahan (@kuasha420) -->
<!-- Corporate Stewardship & Infrastructure: Purrfect Software Limited (PSL) -->
<!-- Governed by: ICARO-42/b Ordinance (Company-Supported Personal IP Framework) -->

# PSL Storage Operations: Workstation & Disk Triage Runbook

This skill establishes empirical, tool-native runbooks for storage triage, cache hygiene, and file system maintenance within Arch Linux and Linux workstation environments.

---

## 1. Bounded-Depth Disk Triage & Space Discovery

### Invariant: Bounded Depth Traversal
Never run unconstrained recursive commands like `du -h /` or broad find commands across root without bounding depth or excluding virtual filesystems (`/proc`, `/sys`, `/dev`). Unbounded traversals cause context saturation, terminal hangs, and false disk full alerts.

### Step 1.1: Filesystem Mount Overview
Check high-level disk capacity and mount points:
```bash
df -hT --exclude-type=tmpfs --exclude-type=devtmpfs
```

### Step 1.2: Bounded-Depth Directory Usage
Locate the largest consumers in root or target mount points bounded to a depth of 1:
```bash
# Root-level consumption (bounded to depth 1, top 20 consumers)
du -h -d 1 / 2>/dev/null | sort -hr | head -n 20

# Target directory consumption (e.g., /var or /home)
du -h -d 1 /var 2>/dev/null | sort -hr | head -n 15
du -h -d 1 /home 2>/dev/null | sort -hr | head -n 15
```

### Step 1.3: Large File Discovery
Locate files larger than 500MB without crossing filesystem boundaries (`-xdev`):
```bash
find / -xdev -type f -size +500M -exec ls -lh {} + 2>/dev/null | sort -k 5 -hr | head -n 20
```

---

## 2. Arch Linux & Pacman Package Cache Hygiene

On Arch Linux and derivative rolling-release systems, package tarballs accumulate in `/var/cache/pacman/pkg/` without automatic eviction.

### Step 2.1: Clean Obsolete Package Versions (`paccache`)
Retain only the current and previous package version (recommended baseline):
```bash
paccache -r
```

### Step 2.2: Remove Uninstalled Package Tarballs
Remove all cached versions of uninstalled packages:
```bash
paccache -ruk0
```

### Step 2.3: Pacman Orphan Removal
Inspect and remove orphaned packages (dependencies no longer required):
```bash
# List orphaned packages
pacman -Qtdq

# Remove orphaned packages with cascade dependencies (guarded against empty target list)
orphans=$(pacman -Qtdq)
if [ -n "$orphans" ]; then
    sudo pacman -Rns $orphans
else
    echo "No orphan packages found."
fi
```

---

## 3. Systemd Journal Vacuuming

Systemd logs can silently consume gigabytes of storage across `/var/log/journal/`.

### Step 3.1: Audit Current Disk Usage
```bash
journalctl --disk-usage
```

### Step 3.2: Vacuum Journal by Size and Retention Time
Constrain journal disk footprint safely:
```bash
# Retain at most 500MB of logs
sudo journalctl --vacuum-size=500M

# Retain at most 14 days of logs
sudo journalctl --vacuum-time=14d
```

### Step 3.3: Verify Journal Daemon Status
```bash
systemctl status systemd-journald --no-pager
```

---

## 4. Docker Storage Reclamation & Prune

Containers, dangling layers, unused networks, and dangling build cache accumulate rapidly during agentic development.

### Step 4.1: Audit Docker Storage Footprint
```bash
docker system df
```

### Step 4.2: Standard Safe Pruning
Remove stopped containers, unused networks, dangling images, and build cache:
```bash
docker system prune -f
```

### Step 4.3: Volume Reclamation (Caution: Data Loss Risk)
Verify volume contents before pruning unreferenced persistent storage:
```bash
# List unused dangling volumes
docker volume ls -qf dangling=true

# Prune unreferenced volumes
docker volume prune -f
```

### Step 4.4: Aggressive Complete Prune
When full recovery is needed (removes all unused images, not just dangling ones):
```bash
docker system prune -a --volumes -f
```

---

## 5. Btrfs Subvolume & Timeshift Snapshot Inspection

On systems utilizing Btrfs for root and system state, snapshots can retain deleted blocks and exhaust free space.

### Step 5.1: Inspect Btrfs Allocation & Free Space
```bash
# Inspect actual allocated vs unallocated chunks
btrfs filesystem df /
btrfs filesystem show
btrfs filesystem usage /
```

### Step 5.2: Inspect Btrfs Subvolumes
```bash
sudo btrfs subvolume list -t /
```

### Step 5.3: Timeshift Snapshot Triage
```bash
# List existing Timeshift snapshots
sudo timeshift --list

# Delete obsolete or bulky snapshot by name/tag
sudo timeshift --delete --snapshot '<SNAPSHOT_NAME>'
```

### Step 5.4: Btrfs Balance (Threshold-Bounded)
Run safe filtered balance to reclaim unallocated block groups without triggering long I/O stalls:
```bash
sudo btrfs balance start -dusage=10 -musage=10 /
```

---

## 6. Modern Kernel NTFS3 Mounting (`ntfs3`)

Modern Linux kernels (5.15+) include the high-performance in-kernel `ntfs3` driver, replacing legacy user-space FUSE `ntfs-3g`.

### Step 6.1: Identify Partition & UUID
```bash
lsblk -f
blkid | grep -i ntfs || [ $? -eq 1 ]
```

### Step 6.2: Mount with Modern `ntfs3`
Mount with proper user ownership, utf8 character set, and correct file/directory permission masks:
```bash
sudo mount -t ntfs3 -o uid=$(id -u),gid=$(id -g),fmask=0133,dmask=0022,iocharset=utf8 /dev/sdXN /mnt/ntfs
```

### Step 6.3: Handling Dirty Bit or Unclean Windows Shutdown
If `ntfs3` refuses to mount read-write due to a dirty bit or Windows Fast Startup hibernation lock:
```bash
# Check and clear dirty flag safely in user space
sudo ntfsfix -d /dev/sdXN
```
Re-attempt mount with `ntfs3`. If problems persist, boot into Windows and disable "Fast Startup" or run `chkdsk /f`.
