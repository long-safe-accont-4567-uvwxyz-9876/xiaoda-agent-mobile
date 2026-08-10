# Terminal Runtime Notice

Xiaoda vendors the `terminal-emulator` component from `termux/termux-app` v0.118.3, commit `5b657c6adf4304e5198951ce815fe0205dcac29c`.

The upstream repository is GPLv3-only as a whole, but its root `LICENSE.md` explicitly identifies the `terminal-emulator` and `terminal-view` libraries as Apache License 2.0 exceptions derived from Android Terminal Emulator. Xiaoda vendors only `terminal-emulator/src/main/java` and `terminal-emulator/src/main/jni`. The upstream exception notice and the Apache License 2.0 text are included beside the vendored source.

The JNI library is rebuilt from the pinned source with Android NDK 22.1.7171670 for `arm64-v8a` and `x86_64`; no Termux application APK, package bootstrap, package manager, shell distribution, or local Agent/Web server is embedded.

Release remains disabled until legal and target-store reviewers provide written approval and the connected-device process-tree test passes. `TERMINAL_RUNTIME_ENABLED` must remain false until those gates are recorded.
