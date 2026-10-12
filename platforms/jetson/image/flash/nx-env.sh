# Shared settings and helpers for the Xavier NX flash scripts (sourced, not run).
#
# Environment (all optional):
#   WORKDIR   work folder on a Linux filesystem (default: ~/jetson-nvme of the user who ran sudo).
#             Under WSL keep it in the Linux home, not under /mnt/c (permissions and symlinks break there).
#   IMG       the delivered image: .img.xz, .img, or the first split part (...img.xz.part0).
#             Default: looked up next to these scripts and in the current folder.
#   BOARD_ENV board identity, so the images are generated with no board attached (no USB reconnects).
#             Default is the devkit this was tested on; read yours from a flash log line
#             "Board ID(3668) version(200) sku(0000) revision(G.0)".

L4T_VERSION=35.6.4
BSP_URL="https://developer.download.nvidia.com/embedded/L4T/r35_Release_v6.4/release/Jetson_Linux_R35.6.4_aarch64.tbz2"
BSP_TBZ="Jetson_Linux_R${L4T_VERSION}_aarch64.tbz2"
IMG_XZ_NAME="jetson-xavier-nx-l4t${L4T_VERSION}-sd.img.xz"
APP_OFFSET_DEFAULT=1484800      # first sector of partition 1 (APP) in the delivered image, used if partx is missing

FLASH_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RUN_USER="${SUDO_USER:-$(id -un)}"
RUN_HOME="$(getent passwd "$RUN_USER" | cut -d: -f6)"
D="${WORKDIR:-$RUN_HOME/jetson-nvme}"
L4T="$D/Linux_for_Tegra"
BOARD_ENV="${BOARD_ENV:-BOARDID=3668 BOARDSKU=0000 FAB=200 BOARDREV=G.0}"

USBIPD_HELP='In an admin PowerShell:  usbipd list | findstr 0955
   If the line does not say "Attached":  usbipd bind --busid <BUSID> --force ; usbipd attach --wsl --busid <BUSID>'

die() { echo "!! $*"; exit 1; }
pause() { echo; echo ">>> $1"; read -rp ">>> Press Enter when ready... " _; }
need_root() { [ "$(id -u)" = 0 ] || die "run as root: sudo bash $0"; }

# Wait (with a pause per try) until a USB id is visible in this Linux/WSL instance.
wait_usb() {  # $1 = usb id, $2 = description
  while ! lsusb | grep -qi "$1"; do
    echo "   Jetson ($2, $1) is NOT visible here yet."
    echo "   On a native Linux host: check the cable and that the board is in that mode."
    echo "   Under WSL: $USBIPD_HELP"
    pause "Attach it, then press Enter to check again (Ctrl+C to quit)"
  done
  echo "   ok: $(lsusb | grep -i "$1")"
}

# Find the delivered image, join split parts, check the .sha256, and write $D/img/nx.img.
prepare_image() {
  [ -s "$D/img/nx.img" ] && { echo "   using $D/img/nx.img"; return 0; }
  local src="${IMG:-}"
  if [ -z "$src" ]; then
    for c in "$FLASH_DIR/$IMG_XZ_NAME" "$PWD/$IMG_XZ_NAME" "$FLASH_DIR/$IMG_XZ_NAME.part0" "$PWD/$IMG_XZ_NAME.part0" \
             "$FLASH_DIR/${IMG_XZ_NAME%.xz}" "$PWD/${IMG_XZ_NAME%.xz}"; do
      [ -e "$c" ] && { src="$c"; break; }
    done
  fi
  [ -n "$src" ] && [ -e "$src" ] || die "image not found: set IMG=/path/to/$IMG_XZ_NAME (or its .part0, or the .img)"
  mkdir -p "$D/img"
  case "$src" in
    *.part0)
      local base="${src%.part0}"
      local parts=(); mapfile -t parts < <(ls -1 "$base".part* | sort -V)
      echo "   joining ${#parts[@]} parts into $D/img/$(basename "$base")"
      cat "${parts[@]}" > "$D/img/$(basename "$base")" || die "join failed"
      [ -e "$base.sha256" ] && cp "$base.sha256" "$D/img/"
      src="$D/img/$(basename "$base")" ;;
  esac
  case "$src" in
    *.xz)
      local sum="$src.sha256"; [ -e "$sum" ] || sum="$(dirname "$src")/$IMG_XZ_NAME.sha256"
      if [ -e "$sum" ]; then
        echo "   checking sha256"
        [ "$(sha256sum "$src" | cut -d' ' -f1)" = "$(cut -d' ' -f1 "$sum")" ] || die "sha256 mismatch for $src"
      else
        echo "   (no .sha256 next to the image, not checked)"
      fi
      echo "   decompressing to $D/img/nx.img"
      xz -dc "$src" > "$D/img/nx.img" || die "xz failed" ;;
    *.img) ln -sf "$(readlink -f "$src")" "$D/img/nx.img" ;;
    *) die "unknown image type: $src" ;;
  esac
}

# Download NVIDIA's L4T BSP if it is not there yet.
prepare_bsp() {
  mkdir -p "$D/bsp"
  [ -s "$D/bsp/$BSP_TBZ" ] && return 0
  echo "   downloading $BSP_TBZ (about 700 MB)"
  curl -fL --retry 4 -o "$D/bsp/$BSP_TBZ.part" "$BSP_URL" && mv "$D/bsp/$BSP_TBZ.part" "$D/bsp/$BSP_TBZ" || die "BSP download failed"
}

# First sector of the image's APP partition (partition 1).
app_offset() {
  local s
  s=$(partx -g -o START -n 1 "$D/img/nx.img" 2>/dev/null | tr -d ' ')
  echo "${s:-$APP_OFFSET_DEFAULT}"
}
