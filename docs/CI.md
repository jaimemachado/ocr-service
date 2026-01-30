# CI / CD and Docker publishing

This repository includes GitHub Actions workflows to run tests and publish Docker images to GitHub Container Registry (GHCR).

Workflows:

- `.github/workflows/ci-docker-publish.yml`: Runs `pytest` and, on success, builds and pushes a multi-arch Docker image to GHCR on pushes to `main`.
- `.github/workflows/release-publish.yml`: Builds and publishes a versioned image when you push a tag like `v1.2.3`.

Image names used in workflows:

- `ghcr.io/jaimemachado/ocr-service:latest`
- `ghcr.io/jaimemachado/ocr-service:<sha>` (CI build)
- `ghcr.io/jaimemachado/ocr-service:<tag>` (release builds)

Required repository settings / secrets:

- `GITHUB_TOKEN`: Provided automatically in GitHub Actions and used for GHCR authentication. No additional secret is required for publishing to GHCR from within GitHub Actions unless you use a separate account.

Repository permissions:

- Ensure the Actions job has `packages: write` permission. The workflows set this permission in the header; if your organization uses a restrictive policy, you may need an admin to allow publishing.

Enabling GHCR access (if needed):

1. Navigate to the repository settings → Packages. Ensure Packages are enabled for your repository or organization.
2. Optionally, grant read access to the package for the organization or specific users.

Notes:

- The workflows use the default `GITHUB_TOKEN` which is sufficient to publish packages to the same repository's GHCR namespace.
- If you want to publish to a Docker Hub account instead, replace the login and tags in the workflow and add `DOCKERHUB_USERNAME` and `DOCKERHUB_TOKEN` to repository secrets.
