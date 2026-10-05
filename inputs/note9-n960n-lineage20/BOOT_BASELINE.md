# Current LineageOS 20 Boot Baseline

Extracted from the running device on 2026-10-05 (local time, Asia/Shanghai). Read-only extraction only — no partition was written on the device.

DEVICE_MODEL=SM-N960N
DEVICE_CODENAME=crownlte
ROM=LineageOS 20
ANDROID_VERSION=13
BUILD_FINGERPRINT=samsung/crownltexx/crownlte:10/QP1A.190711.020/N960FXXSAFWB3:user/release-keys
LINEAGE_BUILD=20.0-20241226-NIGHTLY-crownlte (lineage_crownlte-userdebug 13 TQ3A.230901.001 43404d1434)
KERNEL_VERSION=4.9.118-g6a9461f9460c #1 SMP PREEMPT Thu Dec 26 06:44:45 UTC 2024 aarch64
BOOTLOADER=N960NKSU3FVG4
BASEBAND=N960NKOU3FVG1
HARDWARE_MODEL_EVIDENCE=ro.boot.em.model=SM-N960N; ril.product_code=SM-N960NZPFSKC; bootloader/baseband are N960N builds (ro.product.model=SM-N960F is the LineageOS unified crownlte build model string, not the hardware variant)
BOOT_DEVICE=/dev/block/by-name/BOOT
BOOT_BLOCK_DEVICE=/dev/block/sda10
BOOT_PARTITION_SIZE=57671680
BOOT_FILE=current-lineage20-boot.img
BOOT_SIZE=57671680
PHONE_SHA256=0f389af68199662690e6d1498fea2dd6960b04cb40e6c0f02956d87abde066f8
PC_SHA256=0f389af68199662690e6d1498fea2dd6960b04cb40e6c0f02956d87abde066f8
LOCAL_BOOT_PATH=D:\Doc\Note9-01\boot-backup\current-lineage20-boot.img
GITHUB_REPOSITORY=Sharkecho/Public-Build-Farm
GITHUB_BRANCH=main
GITHUB_BOOT_PATH=inputs/note9-n960n-lineage20/current-lineage20-boot.img
GITHUB_SHA256_PATH=inputs/note9-n960n-lineage20/current-lineage20-boot.img.sha256
GITHUB_BASELINE_PATH=inputs/note9-n960n-lineage20/BOOT_BASELINE.md
PURPOSE=Known-good running LineageOS 20 boot baseline for UAC2 kernel repack
DEVICE_WRITE_PERFORMED=NO

## Extraction notes

- Root access: device has no `su` binary (no Magisk); it is a userdebug LineageOS build, so root was obtained via `adb root` (adbd restarted as root, uid=0). This performs no write to any device partition.
- Extraction: `dd if=/dev/block/sda10 of=/sdcard/current-lineage20-boot.img bs=4096` → 14080+0 records in / 14080+0 records out, 57671680 bytes (exactly BOARD_BOOTIMAGE_PARTITION_SIZE for crownlte).
- Phone-side `sha256sum` and PC-side `Get-FileHash -Algorithm SHA256` agree: `0f389af68199662690e6d1498fea2dd6960b04cb40e6c0f02956d87abde066f8`.
- Boot image header magic verified: `ANDROID!`.
- Evidence logs: `boot-backup/log-root-check.txt`, `boot-backup/log-device-identity.txt`, `boot-backup/log-phone-sha256.txt`.
