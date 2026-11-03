#!/usr/bin/env bash
# Évaluation du décodage vidéo matériel (VAAPI / Quick Sync) du mini PC Nipogi AK2PLUS.
# Usage : bash eval_hw.sh            (Ubuntu 24.04 ou Debian 13, utilisateur avec sudo)
# Résultat : ~/ak2plus-eval/rapport.txt (à renvoyer dans le fil).
set -u
OUT=~/ak2plus-eval; mkdir -p "$OUT"; cd "$OUT"
R=rapport.txt; : > "$R"
log() { echo "== $*" | tee -a "$R"; }

log "Paquets"
sudo apt-get update -qq
sudo apt-get install -y -qq intel-media-va-driver-non-free vainfo intel-gpu-tools ffmpeg mesa-utils pciutils bc >/dev/null \
  || sudo apt-get install -y -qq intel-media-va-driver vainfo intel-gpu-tools ffmpeg mesa-utils pciutils bc >/dev/null

log "Matériel"
{ lscpu | grep -E "Model name|^CPU\(s\)"; free -h | head -2; uname -r; . /etc/os-release; echo "$PRETTY_NAME";
  lspci -nn | grep -iE "vga|display|audio"; sudo dmidecode -t memory 2>/dev/null | grep -E "^\s+(Size|Speed|Type):" | sort -u; } | tee -a "$R"

log "vainfo (profils de décodage)"
vainfo 2>&1 | grep -E "Driver version|VAProfile(H264|HEVC|VP9|AV1).*VLD" | tee -a "$R"

log "Création des vidéos de test (1080p30, 60 s)"
[ -f h264.mp4 ] || ffmpeg -loglevel error -f lavfi -i testsrc2=size=1920x1080:rate=30 -t 60 -c:v libx264 -preset veryfast -b:v 8M -pix_fmt yuv420p h264.mp4
[ -f hevc.mp4 ] || ffmpeg -loglevel error -vaapi_device /dev/dri/renderD128 -f lavfi -i testsrc2=size=1920x1080:rate=30 -t 60 \
  -vf format=nv12,hwupload -c:v hevc_vaapi -b:v 6M hevc.mp4 \
  || ffmpeg -loglevel error -f lavfi -i testsrc2=size=1920x1080:rate=30 -t 60 -c:v libx265 -preset ultrafast -b:v 6M -tag:v hvc1 hevc.mp4

bench() { # $1 fichier, $2 nb de flux, $3 hw|sw, $4 temps réel (re) ou débit max (max)
  local args=(); [ "$3" = hw ] && args=(-hwaccel vaapi -hwaccel_output_format vaapi)
  local re=(); [ "$4" = re ] && re=(-re)
  local t0=$(date +%s.%N); local pids=()
  for i in $(seq "$2"); do ffmpeg -loglevel error -nostats "${args[@]}" "${re[@]}" -i "$1" -f null - & pids+=($!); done
  if [ "$4" = re ]; then sleep 20; top -bn1 | head -12 | tail -6 > top_$1_$2_$3.txt
     sudo timeout 5 intel_gpu_top -o - 2>/dev/null | tail -3 > gpu_$1_$2_$3.txt; fi
  wait "${pids[@]}"; local dt=$(echo "$(date +%s.%N) - $t0" | bc)
  if [ "$4" = max ]; then echo "$1 x$2 $3 : $(echo "scale=0; 1800*$2/$dt" | bc) images/s au total (besoin : $((30*$2)))"
  else echo "$1 x$2 $3 temps réel : $(awk '{s+=$9} END {print s"% CPU (ffmpeg, top)"}' top_$1_$2_$3.txt)"; fi
}

log "Débit maximal de décodage"
for f in h264.mp4 hevc.mp4; do for n in 1 2 3; do bench $f $n hw max | tee -a "$R"; done; bench $f 2 sw max | tee -a "$R"; done
log "Deux flux en temps réel (charge CPU)"
for f in h264.mp4 hevc.mp4; do bench $f 2 hw re | tee -a "$R"; bench $f 2 sw re | tee -a "$R"; done
log "Températures / fréquences"
{ cat /sys/class/thermal/thermal_zone*/temp 2>/dev/null | head -3; grep MHz /proc/cpuinfo | head -4; } | tee -a "$R"
echo; echo "Rapport : $OUT/$R"
