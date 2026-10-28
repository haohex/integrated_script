# Runtime Files

> Files and directories the program creates in the current working directory (cwd).
> Confirmed with the user on 2026-10-28 (branch `refactor/config-dir-no-temp`).

## Rules

- Default config file: `cwd/config/config.json`. `ConfigManager()` without `config_file` uses it and creates `config/` when saving.
- `--config <path>` (explicit `config_file`) is unchanged and does not touch `config/config.json`.
- The old location `cwd/config.json` is **not** read, migrated, or modified. Users who want old settings move the file by hand.
- No `temp/` directory is created. `paths.temp_dir` was removed from the default config and the path settings menu; a leftover `temp_dir` key in an old config file is ignored on load.
- `logs/` (`paths.log_dir`) is unchanged.
- Startup:
  - Source run (`python main.py`, not frozen): no environment check, no workspace initialization.
  - Frozen exe: the silent environment check creates `config/config.json`, `config/default_config.yaml`, and `logs/` only.

## Verification

- `tests/unit/test_settings.py` (default path, old file ignored, `temp_dir` ignored)
- `tests/unit/test_interactive.py::test_exe_startup_creates_only_config_dir_and_logs`
- `tests/unit/test_interactive.py::test_normal_startup_creates_no_temp_or_root_config`

## Not a rule

- The extracted PyInstaller files (`_MEIxxxxxx`) live in a temporary directory chosen by the bootloader, not in cwd; see README §10.1.
