# Windows deployment

The bridge runs on a Windows host on the customer's LAN, the same network as
the recorder. It needs outbound HTTPS to the Rikuy backend and plain HTTP to
the recorder. It needs no inbound ports.

## Build

```
rustup target add x86_64-pc-windows-gnu
./scripts/build-windows.sh
# -> target/x86_64-pc-windows-gnu/release/rikuy-bridge-hikvision.exe  (~3.7 MB)
# -> target/x86_64-pc-windows-gnu/release/rikuy-bridge-ezviz.exe      (~3.3 MB)
```

The script cross-compiles from Linux with **zig** as the C compiler, archiver,
`dlltool` and linker. No MinGW install is needed. It wraps `zig cc` to bridge
the gaps between zig's mingw toolchain and what rustc expects:

| rustc passes | zig wrapper does | Why |
|---|---|---|
| `-lgcc_eh` | `-lunwind` | zig ships LLVM libunwind, which also provides `_GCC_specific_handler` for SEH unwinding |
| `-lmsvcrt` | dropped | zig's mingw runtime is UCRT-based and has no msvcrt import library |
| `-lgcc_s`, `-l:libpthread.a`, `-Wl,--disable-auto-image-base` | dropped | not provided by, or not accepted by, zig's linker |
| raw-dylib imports (`windows-sys`) | `-Cdlltool=zig dlltool` | generates the import libraries |

Each binary is a single static `.exe` with rustls built in. It needs no
OpenSSL and no MSVC redistributable.

**Minimum OS: Windows 10 / Server 2016.** Rust's standard library imports
`ProcessPrng` from `bcryptprimitives.dll`.

## Verification status

- The Linux build and every test pass, including the end-to-end daemon test.
- The Windows build produces valid `PE32+ executable (console) x86-64` files.
- The `.exe` could **not** be run on this machine. The only Wine available is
  5.0.3, which predates `bcryptprimitives.dll`, so the loader fails with
  `c0000135` before `main`. That is a limit of this Wine, not of the binary.
  Running it on Windows 10+ or Wine 9+ is still to do.

## Install as a service (planned)

The bridge is a console program. For a pilot, run it under the built-in task
scheduler or a service wrapper:

```
mkdir C:\ProgramData\Rikuy\bridge
copy rikuy-bridge-hikvision.exe C:\ProgramData\Rikuy\bridge\
# token file: written by enrollment, readable only by the service account
icacls C:\ProgramData\Rikuy\bridge\token /inheritance:r /grant:r "NT AUTHORITY\SYSTEM:R"

rikuy-bridge-hikvision.exe daemon ^
  --backend https://<backend-host> ^
  --token-file C:\ProgramData\Rikuy\bridge\token ^
  --spool C:\ProgramData\Rikuy\bridge\spool ^
  --bridge-id <site-id>
```

The token file is the bridge's own enrollment token and holds no device
password. Device credentials arrive per job from the backend and stay in
memory. The bridge needs no inbound firewall rule.

To do before production:
- native Windows service support (`windows-service` crate) instead of a wrapper;
- automatic restart with back-off;
- spool retention and cleanup;
- code signing.
