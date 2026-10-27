# Security Policy

WaveType is an early Windows preview. Please report vulnerabilities privately so the maintainer can investigate and coordinate a fix before details are made public.

## Versions in scope

| Version | Security report status |
| --- | --- |
| Latest public preview (currently `v0.1.0-beta.1`) | Reports accepted; fixes may be released in a later build. |
| Current `main` branch | Reports accepted for development code. |
| Older builds or branches | No backports are promised. |

There is no stable release yet. The current preview is unsigned and has not completed clean-machine, Microsoft Defender, or runtime network-capture validation. See [release status](docs/RELEASE.md) for the exact checks performed.

## Report a vulnerability

Email **[a.bhattacharya.010805@gmail.com](mailto:a.bhattacharya.010805@gmail.com)** with the subject **WaveType security report**. This is the private reporting route for this repository. Do not open a public issue or pull request containing exploit details, credentials, personal transcripts, or recordings.

Please include what you can:

- The affected WaveType version or commit, Windows version, and installation method.
- A concise description of the impact and the component involved.
- Steps to reproduce or a minimal proof of concept using test data.
- Relevant logs or screenshots with personal information and tokens removed.
- Whether the issue has already been disclosed elsewhere.

Issues in WaveType's local IPC, download verification, model/runtime loading, text insertion, history storage, installer, or bundled dependencies are all appropriate to report here. If the issue is entirely in an upstream dependency, you can also report it to that project's maintainers.

## What happens next

The maintainer will review the report, may ask for more detail, and will work with you on a coordinated disclosure when a fix or mitigation is ready. There is no guaranteed response or release time for this preview. Please allow time for investigation before publishing technical details. If you have already disclosed the issue publicly, include a link in your email.

For ordinary bugs and feature requests, use [GitHub Issues](https://github.com/ABhattacharya-dev/WaveType/issues). Keep Windows security protections enabled; do not disable Defender or add antivirus exclusions to test WaveType.
