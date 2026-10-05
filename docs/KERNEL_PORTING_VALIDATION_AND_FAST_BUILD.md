# Android Kernel Porting: Validation Gate → Fast Build

> Purpose: reusable SOP for bringing kernel changes to a new Android phone/device without repeating the Note9 trial-and-error.
>
> Reference case: Samsung Galaxy Note9 SM-N960N / crownlte / LineageOS 20 / Exynos9810.
>
> Rule: **prove compatibility first; optimize speed only after the first real-device boot/functional validation passes.**

## Phase A — Conservative validation gate (new device / new ROM / new kernel base)

Use this phase whenever any of these changes: device model, ROM base, Android major version, kernel tree/commit, boot layout, toolchain, or major kernel feature.

### A0. Capture the running device as ground truth

Before changing anything, record and archive:

- exact model / codename / SoC
- ROM name, Android version, build fingerprint
- `uname -a` / kernel release
- `/proc/config.gz` when available
- current boot image/kernel Image identity and SHA256 when obtainable
- partition/boot layout needed for recovery
- current feature state (for example UAC2 disabled/enabled)

Do not choose a source tree from model name alone.

### A1. Pin source identity

Map the running kernel to:

- upstream repository
- exact branch
- exact commit
- exact defconfig
- device/vendor dependencies

Freeze these values in CI. Do not build from a moving branch head.

### A2. Reproduce the mature build environment

Prefer a build/toolchain path already proven on the same SoC/kernel family.

For the Note9 reference case this required:

- pinned AOSP Clang
- Apollo/DS-ACK GCC 4.9 companion toolchain
- restored executable permissions and GCC LTO plugin links
- out-of-tree build directories

Verify compiler identity before compiling.

### A3. Diagnostic compile before changing functionality

Run a diagnostic `make -k` build and collect all real compiler failures in one pass.

Classify failures:

1. legacy warnings promoted by `-Werror` → narrowly downgrade only the proven warning class;
2. toolchain/path/linker failures → repair build environment;
3. real source incompatibility → use a proven upstream/mature-project patch where possible;
4. undefined symbols/link failures/assembler failures → remain fatal.

Do **not** globally disable `-Werror`.

Reference Note9 legacy warning classes discovered during validation:

- `unused-variable`
- `strict-prototypes`
- `return-type`
- `format`
- `enum-compare`

Reference Note9 real source incompatibility:

- Samsung DPU clock table used floating-point `double` values while ARM64 kernel compilation used `-mgeneral-regs-only`.
- The mature Apollo implementation converted that table to integer `unsigned long` values. That proven compatibility change was ported instead of inventing a new workaround.

### A4. Build an unchanged baseline first

Before adding the target feature:

- build the pinned baseline kernel;
- require a complete Image/DTB build;
- record SHA256;
- compare config and relevant identity against the running ROM;
- retain logs/evidence.

A successful baseline proves the source/toolchain/build path independently of the new feature.

### A5. Apply the smallest feature delta

Make only the required change.

Note9 UAC2 reference:

`CONFIG_USB_CONFIGFS_F_UAC2=y`

Then require:

- final config contains the requested symbol;
- relevant objects are actually compiled (Note9: `f_uac2.o`, `usb_f_uac2.o`);
- Image builds successfully;
- matching DTB builds from the same source/config/build;
- SHA256 is recorded.

### A6. Package without replacing the ROM's unrelated boot components

For an existing working ROM, preserve its current ramdisk/boot metadata whenever possible.

Preferred model:

current device boot → unpack → replace only validated kernel + matching DTB → repack.

Never mix a kernel/DTB/ramdisk from different ROM bases merely because the device model matches.

### A7. First-device flash gate

Before first flash:

- back up current boot (and DTBO where applicable);
- have a tested recovery path;
- verify model/codename;
- verify package SHA256;
- verify kernel + DTB belong to the same build;
- do not auto-flash an unvalidated package.

After flash validate:

- device boots repeatedly;
- display/touch;
- cellular/baseband;
- Wi-Fi/Bluetooth;
- USB;
- charging;
- audio;
- required new feature;
- SELinux state and critical logs.

Only after this passes is the kernel/base marked **DEVICE-VALIDATED**.

## Phase B — Fast build after device validation

Enter this phase only after Phase A has passed on real hardware.

### B1. Freeze the validated baseline

Tag/archive:

- source commit
- defconfig
- compatibility patch set
- compiler/toolchain versions
- known-good boot/kernel/DTB hashes
- packaging method
- recovery artifact

This becomes the device's kernel SSOT.

### B2. Stop rebuilding proof that is already frozen

Normal development should **not** repeat:

- full diagnostic `make -k`
- unchanged baseline build
- toolchain rediscovery
- source identity research

Those return only when the baseline changes.

### B3. Cache aggressively

Cache/reuse:

- kernel source checkout
- compiler/toolchains
- `out/` build directory
- generated host tools
- packaging tools

Use cache keys tied to source commit + defconfig + toolchain + compatibility-patch version.

### B4. Incremental feature build

Normal loop:

```
change kernel/config
→ incremental build
→ Image + matching DTB
→ config/object assertions
→ SHA256
→ package
→ test
```

Run only affected regression checks.

### B5. Escalation rule

Automatically fall back to Phase A validation if any of these changes:

- device/codename
- ROM/Android major version
- kernel repository/major branch
- pinned baseline commit with substantial upstream changes
- compiler/toolchain family
- boot/partition layout
- major compatibility patch
- previously validated hardware function regresses

## CI layout recommendation

Maintain two explicit workflows:

1. **kernel-validation.yml** — slow, evidence-heavy, baseline + feature build, diagnostic collection.
2. **kernel-fast-build.yml** — cached incremental feature build for a DEVICE-VALIDATED baseline.

Never silently turn the validation workflow into the fast workflow. The validation record is the audit trail for future devices.

## Note9 reference result

The conservative process produced a successful LineageOS 20 Exynos9810 build with:

- baseline kernel build: PASS
- UAC2 kernel build: PASS
- `CONFIG_USB_CONFIGFS_F_UAC2=y`: PASS
- UAC2 objects compiled: PASS
- build/payload integrity hashes recorded

The final real-device boot/functional flash validation remains the boundary between Phase A and Phase B. Do not label the fast path production-safe until that device test passes.
