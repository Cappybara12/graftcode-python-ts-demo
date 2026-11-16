# Changelog

All notable changes to the Graftcode Gateway (`gg`). Binaries are published on
[grft-dev/graftcode-gateway releases](https://github.com/grft-dev/graftcode-gateway/releases);
install or update with `curl -fsSL https://grft.dev/get | sh` (macOS/Linux) or
`iwr https://grft.dev/get | iex` (Windows).

This file collects the notes published with each release and in Graftcode announcements.
Versions whose release page has no notes are marked *(no notes published)*.

## [1.5.0] - 2026-11-09 — Stable

Graftcode leaves Alpha. From the [Stable announcement](https://www.linkedin.com/company/graftcode/posts/):

### Added
- **Native async.** Receivers can expose native async methods (`async def`, `Task<T>`,
  `Promise<T>`, `CompletableFuture<T>`, Guzzle `PromiseInterface`, Ruby async futures); generated
  Grafts expose them as idiomatic async methods, so callers simply `await`. Works across all six
  runtimes in both directions.
- **Built-in observability.** Integrated telemetry for monitoring and troubleshooting.
- **PHP and Ruby.** Full support for both runtimes.
- **Plugins.** Extend Graftcode to messaging and event-driven systems.
- **HTTP/2** support.
- CLI: `--doNotExtractGMA` and `--doNotExtractGVFE`, to supply the module analyzer (GMA) and the
  Graftcode Vision front end (GVFE) yourself instead of extracting the bundled copies.

### Changed
- Security, performance and stability improvements.

## [1.4.14] - 2026-10-30
*(no notes published)*

## [1.4.13] - 2026-10-29
*(no notes published)*

## [1.4.12] - 2026-10-26
*(no notes published)*

## [1.4.11] - 2026-10-23
*(no notes published)*

## [1.4.9] - 2026-10-05
*(no notes published)*

## [1.4.8] - 2026-09-30
*(no notes published)*

## [1.4.7] - 2026-09-23
### Added
- PHP support on macOS, Linux and Windows, x64 and ARM64.
### Fixed
- HTTP/2 server.

## [1.4.6] - 2026-09-16
*(no notes published)*

## [1.4.5] - 2026-09-10
### Changed
- Updated the module analyzer (GMA).
- Higher header-size limit for Graftcode Vision.

## [1.4.3] - 2026-09-03
### Changed
- Updated the module analyzer (GMA).

## [1.4.2] - 2026-08-25
### Added
- `--gatewayName` parameter.
### Fixed
- UTF-8 handling on Windows.
- Handling of parsable types.
- Graftcode Vision fixes.

## [1.4.1] - 2026-08-13
### Added
- `--initMethod` and `--initMethodArgs` flags.

## [1.4.0] - 2026-08-04
### Added
- Support for the new `username:token` Project Key format.

## [1.3.8] - 2026-07-23
### Changed
- Complex type handling.

## [1.3.7] - 2026-07-21
### Added
- Support for comments.

## [1.3.6] - 2026-07-08
### Changed
- `.graftcode` is the default working directory.

## [1.3.5] - 2026-07-07
### Changed
- Updated installation commands.

## [1.3.2] - 2026-07-06
### Changed
- Graftcode Vision updated.

## [1.3.1] - 2026-07-02
### Changed
- Plugin configuration, module analyzer (GMA) and Graftcode Vision updated.

## [1.3.0] - 2026-06-22
### Added
- Plugin handling.

[1.5.0]: https://github.com/grft-dev/graftcode-gateway/releases/tag/v1.5.0
[1.4.14]: https://github.com/grft-dev/graftcode-gateway/releases/tag/v1.4.14
[1.4.13]: https://github.com/grft-dev/graftcode-gateway/releases/tag/v1.4.13
[1.4.12]: https://github.com/grft-dev/graftcode-gateway/releases/tag/v1.4.12
[1.4.11]: https://github.com/grft-dev/graftcode-gateway/releases/tag/v1.4.11
[1.4.9]: https://github.com/grft-dev/graftcode-gateway/releases/tag/v1.4.9
[1.4.8]: https://github.com/grft-dev/graftcode-gateway/releases/tag/v1.4.8
[1.4.7]: https://github.com/grft-dev/graftcode-gateway/releases/tag/v1.4.7
[1.4.6]: https://github.com/grft-dev/graftcode-gateway/releases/tag/v1.4.6
[1.4.5]: https://github.com/grft-dev/graftcode-gateway/releases/tag/v1.4.5
[1.4.3]: https://github.com/grft-dev/graftcode-gateway/releases/tag/v1.4.3
[1.4.2]: https://github.com/grft-dev/graftcode-gateway/releases/tag/v1.4.2
[1.4.1]: https://github.com/grft-dev/graftcode-gateway/releases/tag/v1.4.1
[1.4.0]: https://github.com/grft-dev/graftcode-gateway/releases/tag/v1.4.0
[1.3.8]: https://github.com/grft-dev/graftcode-gateway/releases/tag/v1.3.8
[1.3.7]: https://github.com/grft-dev/graftcode-gateway/releases/tag/v1.3.7
[1.3.6]: https://github.com/grft-dev/graftcode-gateway/releases/tag/v1.3.6
[1.3.5]: https://github.com/grft-dev/graftcode-gateway/releases/tag/v1.3.5
[1.3.2]: https://github.com/grft-dev/graftcode-gateway/releases/tag/v1.3.2
[1.3.1]: https://github.com/grft-dev/graftcode-gateway/releases/tag/v1.3.1
[1.3.0]: https://github.com/grft-dev/graftcode-gateway/releases/tag/v1.3.0
