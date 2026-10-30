/* zedmd_feed: drives a ZeDMD (https://github.com/PPUC/ZeDMD) over its USB serial port.
 *
 * Reads raw RGB888 frames (width x height x 3 bytes, default 128 x 32) from stdin and sends the changed 8x4-pixel
 * zones with the ZeDMD serial protocol, as libzedmd's ZeDMDComm does (same as mpf_godot/zedmd_native.py, the Python
 * fallback). When frames arrive faster than the ZeDMD takes them only the newest one is sent. Linux and macOS (termios);
 * no dependency beyond libc.
 *
 *   zedmd_feed [--port DEV] [--size WxH] [--brightness 0-15] [--probe]     exits when stdin closes; messages on stderr
 *   --probe: connect, say what the ZeDMD is, exit 0 (2 when none answers)
 *   --shades [--color RRGGBB]: frames are w x h bytes, one shade 0-15 per dot (a DMD's 16 shades), drawn as that colour
 *       (default ff730d) scaled by the shade
 *   --serum DIR --rom NAME (--shades, built with build.sh --serum): colour every frame with libserum from
 *       DIR/NAME/NAME.cROMc; a frame the file does not know stays in the plain colour; colour rotations run on libserum's timer
 *
 * Exit code 2: no ZeDMD found or the handshake failed (the caller then falls back to the Python platform).
 */
#include <dirent.h>
#include <errno.h>
#include <fcntl.h>
#include <poll.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <termios.h>
#include <time.h>
#include <unistd.h>
#ifdef WITH_SERUM
#include "serum_glue.h"
#endif

#define ZONE_W 8
#define ZONE_H 4
#define ZONES_BYTE_LIMIT (128 * 3 * 3)
#define CMD_HANDSHAKE 0x0c
#define CMD_ZONES_RGB888 0x04
#define CMD_RENDER 0x06
#define CMD_CLEAR 0x0a
#define CMD_BRIGHTNESS 0x16

static int fd = -1, width = 128, height = 32, write_size = 64;
static const char CTRL[5] = {'Z', 'e', 'D', 'M', 'D'};
static const char FRAMEH[5] = {'F', 'R', 'A', 'M', 'E'};

static int read_timeout(uint8_t *buf, int n, int ms) {
    int got = 0;
    while (got < n) {
        struct pollfd p = {fd, POLLIN, 0};
        if (poll(&p, 1, ms) <= 0) break;
        int r = read(fd, buf + got, n - got);
        if (r <= 0) break;
        got += r;
    }
    return got;
}

static int open_port(const char *dev, int baud_cdc) {
    int f = open(dev, O_RDWR | O_NOCTTY | O_NONBLOCK);
    if (f < 0) return -1;
    struct termios t;
    tcgetattr(f, &t);
    cfmakeraw(&t);
#ifdef B921600
    speed_t s = baud_cdc ? B115200 : B921600;
#else                                           /* macOS: any rate is its number */
    speed_t s = baud_cdc ? 115200 : 921600;
#endif
    cfsetispeed(&t, s);
    cfsetospeed(&t, s);
    t.c_cflag |= CLOCAL | CREAD;
    t.c_cflag &= ~(PARENB | CSTOPB | CSIZE | CRTSCTS);
    t.c_cflag |= CS8;
    t.c_cc[VMIN] = 0;
    t.c_cc[VTIME] = 0;
    tcsetattr(f, TCSANOW, &t);
    tcflush(f, TCIOFLUSH);
    return f;
}

/* Write all of buf in write_size slices (the last zero padded), each answered "ZeDMD" 'A'. 1 = acknowledged. */
static int send_block(const uint8_t *buf, int len) {
    uint8_t piece[1920], ack[6];
    for (int at = 0; at < len; at += write_size) {
        int n = len - at < write_size ? len - at : write_size;
        memset(piece, 0, write_size);
        memcpy(piece, buf + at, n);
        for (int w = 0; w < write_size;) {
            struct pollfd p = {fd, POLLOUT, 0};
            if (poll(&p, 1, 500) <= 0) return -1;
            int r = write(fd, piece + w, write_size - w);
            if (r < 0 && errno != EAGAIN) return -1;
            if (r > 0) w += r;
        }
        if (read_timeout(ack, 6, 100) != 6 || memcmp(ack, CTRL, 5) != 0 || ack[5] != 'A') return 0;
    }
    return 1;
}

static int control(uint8_t *out, uint8_t cmd, const uint8_t *payload, int len) {
    memcpy(out, CTRL, 5);
    out[5] = cmd;
    out[6] = len >> 8;
    out[7] = len & 255;
    out[8] = 0;
    if (len) memcpy(out + 9, payload, len);
    return 9 + len;
}

static int handshake(void) {
    uint8_t buf[64], reply[64];
    tcflush(fd, TCIFLUSH);
    memset(buf, 0, sizeof buf);
    memcpy(buf, FRAMEH, 5);
    control(buf + 5, CMD_HANDSHAKE, NULL, 0);
    if (write(fd, buf, 64) != 64) return 0;
    if (read_timeout(reply, 64, 500) != 64 || memcmp(reply, CTRL, 4) != 0 || reply[57] != 'R') return 0;
    int w = reply[4] + reply[5] * 256, h = reply[6] + reply[7] * 256, ws = reply[11] + reply[12] * 256;
    write_size = (ws >= 32 && ws <= 1920) ? ws : 64;
    fprintf(stderr, "ZeDMD %dx%d firmware %d.%d.%d\n", w, h, reply[8], reply[9], reply[10]);
    if (w != width || h != height) fprintf(stderr, "warning: ZeDMD is %dx%d, frames are %dx%d\n", w, h, width, height);
    return 1;
}

static int command_block(uint8_t cmd, const uint8_t *payload, int len) {
    uint8_t buf[64];
    memcpy(buf, FRAMEH, 5);
    int n = 5 + control(buf + 5, cmd, payload, len);
    return send_block(buf, n);
}

static int send_packet(const uint8_t *zones, int len) {
    uint8_t buf[ZONES_BYTE_LIMIT + 64];
    memcpy(buf, FRAMEH, 5);
    int n = 5 + control(buf + 5, CMD_ZONES_RGB888, zones, len);
    n += control(buf + n, CMD_RENDER, NULL, 0);
    return send_block(buf, n);
}

/* The changed zones of frame against prev (NULL: all), in packets of at most ZONES_BYTE_LIMIT bytes. 1 = all sent. */
static int send_frame(const uint8_t *frame, const uint8_t *prev) {
    int zones_x = width / ZONE_W, count = zones_x * (height / ZONE_H);
    uint8_t cur[ZONES_BYTE_LIMIT + 128];
    int len = 0;
    for (int z = 0; z < count; z++) {
        int x = z % zones_x * ZONE_W, y = z / zones_x * ZONE_H;
        uint8_t px[ZONE_W * ZONE_H * 3];
        int same = prev != NULL, lit = 0;
        for (int r = 0; r < ZONE_H; r++) {
            const uint8_t *row = frame + ((y + r) * width + x) * 3;
            memcpy(px + r * ZONE_W * 3, row, ZONE_W * 3);
            if (same && memcmp(row, prev + ((y + r) * width + x) * 3, ZONE_W * 3)) same = 0;
        }
        if (same) continue;
        for (int i = 0; i < ZONE_W * ZONE_H * 3 && !lit; i++) lit = px[i] != 0;
        int need = lit ? 1 + ZONE_W * ZONE_H * 3 : 1;
        if (len + need > ZONES_BYTE_LIMIT) {
            int ok = send_packet(cur, len);
            if (ok != 1) return ok;
            len = 0;
        }
        if (lit) {
            cur[len++] = z;
            memcpy(cur + len, px, sizeof px);
            len += sizeof px;
        } else {
            cur[len++] = z + 128;
        }
    }
    return len ? send_packet(cur, len) : 1;
}

static int connect_port(const char *named) {
    char path[300];
    const char *names[64];
    int n = 0;
    static char store[64][280];
    if (named) {
        names[n++] = named;
    } else {
        const char *dirs[] = {"/dev"};
        DIR *d = opendir(dirs[0]);
        struct dirent *e;
        while (d && (e = readdir(d)) && n < 64) {
            if (!strncmp(e->d_name, "ttyACM", 6) || !strncmp(e->d_name, "ttyUSB", 6) ||
                !strncmp(e->d_name, "cu.usbserial", 12) || !strncmp(e->d_name, "cu.usbmodem", 11)) {
                snprintf(store[n], sizeof store[n], "/dev/%s", e->d_name);
                names[n] = store[n];
                n++;
            }
        }
        if (d) closedir(d);
    }
    for (int i = 0; i < n; i++) {
        snprintf(path, sizeof path, "%s", names[i]);
        for (int cdc = 0; cdc < 2; cdc++) {     /* the ESP32-S3's own USB runs at 115200, the others at 921600 */
            fd = open_port(path, cdc);
            if (fd < 0) break;
            if (handshake()) return 1;
            close(fd);
            fd = -1;
        }
    }
    return 0;
}

int main(int argc, char **argv) {
    const char *port = NULL;
    int brightness = -1, probe = 0, shades = 0;
    const char *serum_dir = NULL, *serum_rom = NULL;
    uint8_t ramp[16 * 3];
    unsigned rgb0 = 0xff730d;
    for (int i = 1; i < argc; i++) {
        if (!strcmp(argv[i], "--shades")) shades = 1;
        else if (!strcmp(argv[i], "--color") && i + 1 < argc) rgb0 = strtoul(argv[++i], NULL, 16);
        else if (!strcmp(argv[i], "--serum") && i + 1 < argc) serum_dir = argv[++i];
        else if (!strcmp(argv[i], "--rom") && i + 1 < argc) serum_rom = argv[++i];
        else
        if (!strcmp(argv[i], "--port") && i + 1 < argc) port = argv[++i];
        else if (!strcmp(argv[i], "--size") && i + 1 < argc) sscanf(argv[++i], "%dx%d", &width, &height);
        else if (!strcmp(argv[i], "--probe")) probe = 1;
        else if (!strcmp(argv[i], "--brightness") && i + 1 < argc) brightness = atoi(argv[++i]);
    }
    if (width % ZONE_W || height % ZONE_H || width * height * 3 > 256 * 64 * 3) {
        fprintf(stderr, "bad size %dx%d\n", width, height);
        return 1;
    }
    for (int n = 0; n < 16; n++) {
        ramp[n * 3] = (rgb0 >> 16 & 255) * n / 15;
        ramp[n * 3 + 1] = (rgb0 >> 8 & 255) * n / 15;
        ramp[n * 3 + 2] = (rgb0 & 255) * n / 15;
    }
    if (serum_dir && (!shades || !serum_rom)) {
        fprintf(stderr, "--serum needs --shades and --rom\n");
        return 1;
    }
#ifndef WITH_SERUM
    if (serum_dir) {
        fprintf(stderr, "this zedmd_feed was built without Serum (build.sh --serum)\n");
        return 1;
    }
#endif
    if (!connect_port(port)) {
        fprintf(stderr, "no ZeDMD found\n");
        return 2;
    }
    if (probe) return 0;
    if (brightness >= 0) {
        uint8_t b = brightness > 15 ? 15 : brightness;
        command_block(CMD_BRIGHTNESS, &b, 1);
    }
    size_t fsize = (size_t)width * height * 3;                  /* the RGB frame sent to the ZeDMD */
    size_t isize = shades ? (size_t)width * height : fsize;     /* one input frame */
    uint8_t *in = malloc(isize * 8), *src = malloc(isize), *last = malloc(fsize), *prev_ok = NULL;
    int rotate_ms = 0, serum_on = 0;
    (void)serum_on;
    struct timespec rot_at = {0, 0};
#ifdef WITH_SERUM
    if (serum_dir) {
        if (!serum_open(serum_dir, serum_rom, width, height)) return 1;
        serum_on = 1;
    }
#endif
    size_t have = 0;
    int ok = 1;
    for (;;) {
        /* read what is there; while more waits, keep reading so that only the newest complete frame is sent */
        struct pollfd p = {0, POLLIN, 0};
        int wait = 3000, rotate = 0;
        if (rotate_ms > 0) {
            struct timespec now;
            clock_gettime(CLOCK_MONOTONIC, &now);
            wait = (rot_at.tv_sec - now.tv_sec) * 1000 + (rot_at.tv_nsec - now.tv_nsec) / 1000000;
            if (wait < 0) wait = 0;
        }
        if (poll(&p, 1, wait) == 0) {
            if (rotate_ms <= 0) continue;
            rotate = 1;                         /* libserum's colour rotation is due */
        }
        int eof = 0;
        while (!rotate) {
            ssize_t r = read(0, in + have, isize * 8 - have);
            if (r <= 0) { eof = 1; break; }
            have += r;
            size_t whole = have / isize * isize;
            if (whole) {
                memcpy(src, in + whole - isize, isize);
                prev_ok = src;
                memmove(in, in + whole, have - whole);
                have -= whole;
            }
            p.revents = 0;
            if (!(poll(&p, 1, 0) > 0 && have < isize * 8)) break;
        }
        if (eof && !prev_ok) break;
        if (prev_ok || rotate) {
            static uint8_t *sent = NULL;
            int black = 1, known = 0;
            if (rotate) {
#ifdef WITH_SERUM
                serum_rotate(last, &rotate_ms);
                known = 1;
#endif
            } else if (!shades) {
                memcpy(last, src, fsize);
            } else {
                known = 0;
#ifdef WITH_SERUM
                if (serum_on) {
                    int r = serum_colorize(src, last, &rotate_ms);
                    known = r;                  /* 1 coloured, 2 the same frame as before: last stands */
                    if (r == 0) rotate_ms = 0;
                }
#endif
                if (known == 0)
                    for (size_t i = 0; i < isize; i++) memcpy(last + i * 3, ramp + (src[i] & 15) * 3, 3);
            }
            if (rotate_ms > 0) {
                clock_gettime(CLOCK_MONOTONIC, &rot_at);
                rot_at.tv_nsec += (long)rotate_ms * 1000000L;
                rot_at.tv_sec += rot_at.tv_nsec / 1000000000L;
                rot_at.tv_nsec %= 1000000000L;
            }
            for (size_t i = 0; i < fsize && black; i++) black = last[i] == 0;
            if (!sent) sent = calloc(1, fsize), ok = 0;
            if (black) {
                if (!ok || memcmp(sent, last, fsize)) command_block(CMD_CLEAR, NULL, 0);
                ok = 1;
                memcpy(sent, last, fsize);
            } else {
                int r = send_frame(last, ok ? sent : NULL);
                if (r < 0) { fprintf(stderr, "ZeDMD lost\n"); return 3; }
                ok = r == 1;
                if (ok) memcpy(sent, last, fsize);
            }
            prev_ok = NULL;
        }
        if (eof) break;
    }
    return 0;
}
