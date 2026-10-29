# Contributing to XL View

Please open an issue before starting a large feature. Include the problem you want to solve and the expected controller behavior.

For bugs, include XL View version, Windows version, Launch Control XL 3 firmware, relevant MIDI port names, other MIDI applications running, and reproducible steps. Remove private paths or mappings from logs before posting them. Never post credentials.

## Development

Follow [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md). Keep UI text in English. Run the offline tests before submitting a pull request. Explain what changed, how you tested it, and whether real hardware was involved.

Tests must not open physical MIDI ports, write controller slots, or modify a user's DAW project. Hardware checks must use an explicitly chosen expendable slot with a backup. Do not treat a software-only test as hardware verification.

Preserve the distinction between the selected editing slot, the active hardware mode, and an unsent draft. Editing or sending must not unnecessarily close the inspector, discard selections, or stop incoming feedback. Keep user presets, backups, local settings, captures, build products and credentials out of commits.

Contributions are accepted under the repository's MIT License. Third-party code and assets must retain their applicable notices.
