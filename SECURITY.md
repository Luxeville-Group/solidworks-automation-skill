# Security policy

## Supported versions

Security fixes prioritize the current fork's main branch. Upstream release evidence does not establish that a localized binary has been built or published.

## Reporting vulnerabilities

Report credential exposure, arbitrary file writes, command injection, approval bypass or uncontrolled CAD automation privately through GitHub Security Advisories where available. If private reporting is unavailable, request a private contact without posting vulnerability details. Do not attach API keys, company drawings, task queues or complete logs to public issues.

## Trust boundaries

- CAD Studio does not store AI API keys; Agent CLI or CC Switch handles authentication.
- CAD operations, cross-directory access, network operations, deletion and Git pushes pass through the existing policy gates.
- AI output does not replace a mechanical engineer's checks of dimensions, materials, loads, safety and manufacturing.
- Check release SHA-256 values and publisher provenance. A fork release needs its own trusted signing/update setup; do not disable signature verification to accept it.
