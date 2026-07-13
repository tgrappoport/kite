# Documentation Deployment Notes (tgrappoport/kite fork)

This file is internal maintenance documentation for this fork. It lives outside `docs/` (mkdocs'
`docs_dir`) so that it is never built or published as part of the KITE documentation site itself.

## Live site

The fork's documentation is published at:

<https://tgrappoport.github.io/kite/>

## Deployment method: manual, not CI

The repository ships with two automated deploy pipelines intended to publish the docs on every push to
`master`:

- `.github/workflows/ci.yml` — runs `mkdocs gh-deploy --force` on GitHub Actions, publishing to GitHub
  Pages.
- `.gitlab-ci.yml` — builds the site with `mkdocs build --site-dir public` for GitLab Pages (unaffected by
  the issue below; not used by this fork).

On this fork, the GitHub Actions pipeline has not been made to work reliably:

1. **First failure mode:** the default `GITHUB_TOKEN` granted to Actions on a newly created repository has
   read-only permissions. `mkdocs gh-deploy` needs to push a new `gh-pages` branch, which requires write
   access. Fixed by setting **Settings → Actions → General → Workflow permissions → Read and write
   permissions**.
2. **Second failure mode:** after the permissions fix, subsequent runs completed with a `startup_failure`
   conclusion — the job never started, and no logs are available to diagnose why. This was not
   investigated further, since the manual deployment method below is reliable and low-effort.

As a result, **the documentation site is currently deployed manually** rather than automatically. Anyone
maintaining this fork should either keep following the manual process below, or revisit the Actions
`startup_failure` before relying on automatic deployment again.

## How to redeploy manually

From the repository root, with `mkdocs` and `mkdocs-material` installed (`pip install mkdocs
mkdocs-material`):

```bash
mkdocs gh-deploy --remote-name tgrappoport --remote-branch gh-pages --force
```

`--remote-name tgrappoport` is required because the fork's push-capable git remote is not named `origin`
(see [Remote setup](#remote-setup) below); the default `origin` remote is read-only, pointing at the
upstream `quantum-kite/kite` repository. Run this any time after documentation changes have been committed
(and ideally pushed) to `master`, to keep the published site in sync.

## A known gotcha: `docs/CNAME`

`docs/CNAME`, inherited from the upstream repository, points to the custom domain `quantum-kite.com`. Any
built site that includes this file causes GitHub Pages to attempt to serve the fork under that domain
instead of the default `tgrappoport.github.io/kite` — and since that domain is not verified for this
account, this breaks the deployment rather than simply being ignored.

This file was removed from the fork on 2026-07-13 (commit `dff1626`). If it is ever reintroduced — for
example, by merging updates from the upstream repository — it must be removed again before running
`mkdocs gh-deploy`, or the Pages configuration will need to be corrected afterward in **Settings → Pages**.

## Remote setup

This fork is pushed to via a dedicated git remote and SSH identity, kept separate from the read-only
`origin` remote pointing at `quantum-kite/kite`:

```
origin       https://github.com/quantum-kite/kite.git   (fetch/push; read-only in practice)
tgrappoport  git@github-tgrappoport:tgrappoport/kite.git (fetch/push; read-write)
```

The `github-tgrappoport` SSH host alias is configured in `~/.ssh/config` on the machine this was set up on,
using a dedicated key (`~/.ssh/id_ed25519_tgrappoport`) added to the `tgrappoport` GitHub account. Anyone
else maintaining this fork from a different machine will need to add their own SSH key to the
`tgrappoport` account and configure an equivalent remote before they can push or run `mkdocs gh-deploy`.
