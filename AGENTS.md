# Public Build Farm — Agent Routing

This repository is shared build infrastructure. The engineering control plane is `Sharkecho/Engineering-Control`.

## Active project routes

### LiveOS / LineageOS 20 Baseline
- Workflow: `.github/workflows/note9-liveos-lineage20-baseline.yml`
- Project identity: LiveOS Base OS for Note9/crownlte.
- Control-plane definition: `Engineering-Control/projects/LiveOS.md`
- This is NOT the Note9 UAC2 kernel project.
- Goal: reproducible baseline OS artifact; upper LiveOS remains separable.
- On failure: inspect the exact Actions run and diagnostic artifacts before modifying or rerunning.

### Note9 Kernel / UAC2
- Workflow: `.github/workflows/note9-01-kernel-build.yml`
- Private source repository: `Sharkecho/note9-01`
- Control-plane definition: `Engineering-Control/projects/Note9-Kernel.md`
- This is NOT LiveOS.
- Private source, credentials and Samsung source archives must never be exposed through this public repository.

## Shared rules
1. Determine which workflow/project owns the task before changing anything.
2. Never transfer assumptions, patches, build steps or acceptance criteria between LiveOS and Note9 Kernel without an explicit integration task.
3. Diagnose CI from run/job/log/artifact evidence.
4. Do not blindly rerun deterministic failures.
5. Make minimal changes and validate only the affected path.
6. Keep secrets/private source out of this public repository.
7. A build task is complete only when its required artifact and verification gates pass.


## CI-Fixer branch policy
- Automated repair MUST start from the exact failing commit and use `ci-fix/<run-id>-<description>`.
- Automated repair MUST NOT push directly to `main`.
- Automated repair MUST NOT auto-merge.
- Before PR delivery, compare the failing SHA with current `main`.
- If `main` moved, rebase/update only when clean and rerun affected validation.
- Any overlapping/semantic conflict => STOP with `NEEDS_HUMAN_REVIEW`; never guess.
- PR merge requires human approval.
