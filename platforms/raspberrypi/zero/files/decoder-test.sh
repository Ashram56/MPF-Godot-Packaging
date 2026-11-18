#!/usr/bin/env bash
# Measures the opening of the Zero's H.264 decoder (hardware v4l2m2m-copy against software) on the topper's logo video.
# Run on the Zero:  bash decoder-test.sh > /tmp/decoder-test.txt 2>&1 ; cat /tmp/decoder-test.txt
f="${1:-/var/lib/pup-topper/media/Background - Topper/TronLegacyLogo.mp4}"
sudo systemctl stop pup-topper
sleep 3
echo "service: $(systemctl is-active pup-topper)"
ls -la "$f"
echo "=== hardware (v4l2m2m-copy), 0.5 s ==="
time mpv --no-config --vo=null --ao=null --hwdec=v4l2m2m-copy --length=0.5 --msg-level=all=v "$f" 2>&1 | grep -iE "v4l2|hwdec|decoder|Using|fail|VO:|first|Playing|fps|Video" | head -30
echo "=== software, 0.5 s ==="
time mpv --no-config --vo=null --ao=null --hwdec=no --length=0.5 "$f" > /dev/null 2>&1
echo "=== kernel ==="
dmesg | grep -iE "cma|codec|v4l2|vchiq" | tail -15
vcgencmd get_mem gpu
grep -i cma /proc/meminfo
free -m
sudo systemctl start pup-topper
