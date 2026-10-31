#!/usr/bin/env bash
# Cross-compile the bridge binaries for a customer Windows host
# (x86_64-pc-windows-gnu) using zig as the C compiler and linker, so no MinGW
# install is needed. Requires: rustup target x86_64-pc-windows-gnu, zig >= 0.11.
set -euo pipefail
cd "$(dirname "$0")/.."

TARGET=x86_64-pc-windows-gnu
WRAP="$PWD/target/zig-wrappers"
mkdir -p "$WRAP"

# zig rejects some flags rustc passes for the gnu target; filter them out.
# zig ships a UCRT-based mingw runtime and no msvcrt import library, so
# -lmsvcrt is dropped and zig's own C runtime is linked instead. libgcc_eh
# (unwinding) is replaced by LLVM libunwind, which zig builds for the target
# and which also provides the SEH personality hook (_GCC_specific_handler).
cat > "$WRAP/cc" <<'EOF'
#!/usr/bin/env bash
args=()
for a in "$@"; do
  case "$a" in
    -lgcc_eh) args+=("-lunwind") ;;
    -lgcc_s|-l:libpthread.a|-lmsvcrt|--target=*|-Wl,--disable-auto-image-base) ;;
    *) args+=("$a") ;;
  esac
done
exec zig cc -target x86_64-windows-gnu "${args[@]}"
EOF
cat > "$WRAP/ar" <<'EOF'
#!/usr/bin/env bash
exec zig ar "$@"
EOF
cat > "$WRAP/dlltool" <<'EOF'
#!/usr/bin/env bash
exec zig dlltool "$@"
EOF
chmod +x "$WRAP/cc" "$WRAP/ar" "$WRAP/dlltool"

export CC_x86_64_pc_windows_gnu="$WRAP/cc"
export AR_x86_64_pc_windows_gnu="$WRAP/ar"
export CARGO_TARGET_X86_64_PC_WINDOWS_GNU_LINKER="$WRAP/cc"
# windows-sys uses raw-dylib import libraries, generated with dlltool.
export CARGO_TARGET_X86_64_PC_WINDOWS_GNU_RUSTFLAGS="-Cdlltool=$WRAP/dlltool"

cargo build --release --target "$TARGET" -p rikuy-bridge-hikvision -p rikuy-bridge-ezviz "$@"
ls -l "target/$TARGET/release/"*.exe
