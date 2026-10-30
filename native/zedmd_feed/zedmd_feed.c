/* zedmd_feed: drives a ZeDMD (https://github.com/PPUC/ZeDMD) over its USB serial port.
 *
 * Reads raw RGB888 frames (width x height x 3 bytes, default 128 x 32) from stdin and sends the changed 8x4-pixel
 * zones with the ZeDMD serial protocol, as libzedmd's ZeDMDComm does (same as mpf_godot/zedmd_native.py, the Python
 * fallback). When frames arrive faster than the ZeDMD takes them only the newest one is sent. Linux and macOS (termios);
 * no dependency beyond libc.
 *
 *   zedmd_feed [--port DEV] [--size WxH] [--brightness 0-15] [--probe]     exits when stdin closes; messages on stderr
 *   --probe: connect, say what the ZeDMD is, exit 0 (2 when none answers)
 *   --shades [--color RRGGBB] [--serum LIB DIR ROM]
 *       the input is the game's DMD as one byte per dot, 0-15 (a DMD's 16 shades), not RGB888. Without --serum the shades
 *       scale --color (default ff730d). With --serum the colour comes from a Serum colourisation: LIB is libserum's
 *       shared library, loaded as it is (dlopen, unmodified), DIR the folder holding ROM/ROM.cRZ (or .cROM), ROM the
 *       colourisation's name. A frame that Serum does not know keeps the single colour; colour rotations run on a timer.
 *
 * Exit code 2: no ZeDMD found or the handshake failed (the caller then falls back to the Python platform).
 */
#include <dirent.h>
#include <dlfcn.h>
#include <errno.h>
#include <fcntl.h>
#include <poll.h>
#include <signal.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <termios.h>
#include <unistd.h>

#define ZONE_W 8
#define ZONE_H 4
#define ZONES_BYTE_LIMIT (128 * 3 * 3)
#define HANDSHAKES 8
#define CMD_HANDSHAKE 0x0c
#define CMD_ZONES_RGB888 0x04
#define CMD_RENDER 0x06
#define CMD_CLEAR 0x0a
#define CMD_BRIGHTNESS 0x16

static int fd = -1, width = 128, height = 32, write_size = 64;

/* Serum (https://github.com/PPUC/libserum), loaded with dlopen: only the C functions and the frame struct are used, as
 * declared in its serum.h; the part of the struct read here (up to nocolors) is copied below. */
typedef struct {
    uint8_t *frame, *palette, *rotations;
    uint16_t *frame32;
    uint32_t width32;
    uint16_t *rotations32, *rotationsinframe32;
    uint8_t *modifiedelements32;
    uint16_t *frame64;
    uint32_t width64;
    uint16_t *rotations64, *rotationsinframe64;
    uint8_t *modifiedelements64;
    uint32_t SerumVersion;
    uint8_t flags;
    uint32_t nocolors;
} SerumFrame;
#define SERUM_FLAG_32P 1
#define SERUM_NO_FRAME 0xffffffffu
#define SERUM_SAME_FRAME 0xfffffffeu
static SerumFrame *(*serum_load)(const char *, const char *, uint8_t);
static uint32_t (*serum_colorize)(uint8_t *);
static uint32_t (*serum_rotate)(void);
static void (*serum_dispose)(void);
static SerumFrame *serum;
static int serum_known;                         /* 1 once a frame of the colourisation was matched */
static uint8_t mono[16 * 3];                    /* shade -> colour when Serum does not colour the frame */
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
    uint8_t buf[HANDSHAKES * 64], reply[64];
    tcflush(fd, TCIFLUSH);
    memset(buf, 0, sizeof buf);
    memcpy(buf, FRAMEH, 5);
    control(buf + 5, CMD_HANDSHAKE, NULL, 0);
    for (int i = 1; i < HANDSHAKES; i++) memcpy(buf + i * 64, buf, 64);
    /* A ZeDMD on a Pico 2 (firmware 6.1.3) reads in blocks of its write size, 512 bytes, the handshake included, and
     * answers only when the block is complete; one 64-byte handshake is answered at random. Eight in one write fill
     * a 512-byte block, and a firmware with 64-byte blocks answers the first and ignores the others. */
    if (write(fd, buf, sizeof buf) != (ssize_t)sizeof buf) return 0;
    if (read_timeout(reply, 64, 500) != 64 || memcmp(reply, CTRL, 4) != 0 || reply[57] != 'R') return 0;
    usleep(150000);                                 /* the answers to the other handshakes, if any */
    tcflush(fd, TCIFLUSH);
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

/* The monochrome picture: each shade scales the colour. */
static void mono_frame(const uint8_t *shades, uint8_t *rgb) {
    for (int i = 0; i < width * height; i++) memcpy(rgb + i * 3, mono + (shades[i] & 15) * 3, 3);
}

/* The RGB picture Serum returned (RGB565 for version 2, a palette for version 1). 1 = taken. */
static int serum_picture(uint8_t *rgb) {
    int n = width * height;
    if (serum->SerumVersion >= 2) {
        if (!serum->frame32 || (int)serum->width32 != width) return 0;
        for (int i = 0; i < n; i++) {
            uint16_t c = serum->frame32[i];
            rgb[i * 3] = ((c >> 11) & 31) * 255 / 31;
            rgb[i * 3 + 1] = ((c >> 5) & 63) * 255 / 63;
            rgb[i * 3 + 2] = (c & 31) * 255 / 31;
        }
        return 1;
    }
    if (!serum->frame || !serum->palette) return 0;
    for (int i = 0; i < n; i++) memcpy(rgb + i * 3, serum->palette + serum->frame[i] * 3, 3);
    return 1;
}

/* Colour a frame of shades. Returns the rotation timer in ms (0: none). */
static int colorize(const uint8_t *shades, uint8_t *rgb, uint8_t *held) {
    if (!serum) { mono_frame(shades, rgb); return 0; }
    static uint8_t in[256 * 64];
    int four = serum->nocolors == 4;
    for (int i = 0; i < width * height; i++) in[i] = four ? (shades[i] * 3 + 7) / 15 : shades[i];
    uint32_t r = serum_colorize(in);
    if (r == SERUM_SAME_FRAME) { memcpy(rgb, held, (size_t)width * height * 3); return 0; }
    if (r == SERUM_NO_FRAME) {                  /* not a frame of the colourisation */
        mono_frame(shades, rgb);
        return 0;
    }
    if (!serum_picture(rgb)) mono_frame(shades, rgb);
    else serum_known = 1;
    return (int)(r & 0xffff);
}

static int load_serum(const char *lib, const char *dir, const char *rom) {
    void *h = dlopen(lib, RTLD_NOW | RTLD_LOCAL);
    if (!h) { fprintf(stderr, "serum: %s\n", dlerror()); return 0; }
    serum_load = dlsym(h, "Serum_Load");
    serum_colorize = dlsym(h, "Serum_Colorize");
    serum_rotate = dlsym(h, "Serum_Rotate");
    serum_dispose = dlsym(h, "Serum_Dispose");
    if (!serum_load || !serum_colorize || !serum_rotate) { fprintf(stderr, "serum: %s is not libserum\n", lib); return 0; }
    serum = serum_load(dir, rom, SERUM_FLAG_32P);
    if (!serum) { fprintf(stderr, "serum: no colourisation %s in %s, single colour\n", rom, dir); return 0; }
    fprintf(stderr, "serum: %s loaded (version %u, %u shades)\n", rom, serum->SerumVersion, serum->nocolors);
    return 1;
}

int main(int argc, char **argv) {
    signal(SIGPIPE, SIG_IGN);                   /* a caller that closes our stderr must not kill us on a message */
    const char *port = NULL;
    int brightness = -1, probe = 0, shades = 0;
    const char *lib = NULL, *serum_dir = NULL, *serum_rom = NULL;
    unsigned colour = 0xff730d;
    for (int i = 1; i < argc; i++) {
        if (!strcmp(argv[i], "--shades")) { shades = 1; continue; }
        if (!strcmp(argv[i], "--color") && i + 1 < argc) { colour = strtoul(argv[++i], NULL, 16); continue; }
        if (!strcmp(argv[i], "--serum") && i + 3 < argc) { lib = argv[++i]; serum_dir = argv[++i]; serum_rom = argv[++i]; continue; }
        if (!strcmp(argv[i], "--port") && i + 1 < argc) port = argv[++i];
        else if (!strcmp(argv[i], "--size") && i + 1 < argc) sscanf(argv[++i], "%dx%d", &width, &height);
        else if (!strcmp(argv[i], "--probe")) probe = 1;
        else if (!strcmp(argv[i], "--brightness") && i + 1 < argc) brightness = atoi(argv[++i]);
    }
    if (width % ZONE_W || height % ZONE_H || width * height * 3 > 256 * 64 * 3) {
        fprintf(stderr, "bad size %dx%d\n", width, height);
        return 1;
    }
    if (!connect_port(port)) {
        fprintf(stderr, "no ZeDMD found\n");
        return 2;
    }
    if (probe) return 0;
    if (brightness >= 0) {
        uint8_t b = brightness > 15 ? 15 : brightness;
        command_block(CMD_BRIGHTNESS, &b, 1);
    }
    for (int n = 0; n < 16; n++) {
        mono[n * 3] = (colour >> 16 & 255) * n / 15;
        mono[n * 3 + 1] = (colour >> 8 & 255) * n / 15;
        mono[n * 3 + 2] = (colour & 255) * n / 15;
    }
    if (lib) { shades = 1; load_serum(lib, serum_dir, serum_rom); }
    size_t rsize = (size_t)width * height * 3;          /* the RGB picture sent to the ZeDMD */
    size_t fsize = shades ? (size_t)width * height : rsize;     /* one input frame */
    uint8_t *rgb = malloc(rsize), *held = calloc(1, rsize);
    int rotate_ms = 0;
    uint8_t *sent = NULL;
    uint8_t *in = malloc(fsize * 8), *last = malloc(fsize), *prev_ok = NULL;
    size_t have = 0;
    int ok = 1;
    for (;;) {
        /* read what is there; while more waits, keep reading so that only the newest complete frame is sent */
        struct pollfd p = {0, POLLIN, 0};
        int idle = poll(&p, 1, rotate_ms > 0 ? rotate_ms : 3000);
        if (idle == 0 && rotate_ms > 0 && serum) {      /* a colour rotation step: same frame, new colours */
            uint32_t r = serum_rotate();
            rotate_ms = (int)(r & 0xffff);
            if (serum_picture(rgb)) {
                memcpy(held, rgb, rsize);
                int s2 = send_frame(rgb, NULL);
                if (s2 < 0) { fprintf(stderr, "ZeDMD lost\n"); return 3; }
                if (!sent) sent = calloc(1, rsize);
                ok = s2 == 1;
                if (ok) memcpy(sent, rgb, rsize);
            }
            continue;
        }
        if (idle == 0) continue;
        int eof = 0;
        do {
            ssize_t r = read(0, in + have, fsize * 8 - have);
            if (r <= 0) { eof = 1; break; }
            have += r;
            size_t whole = have / fsize * fsize;
            if (whole) {
                memcpy(last, in + whole - fsize, fsize);
                prev_ok = last;
                memmove(in, in + whole, have - whole);
                have -= whole;
            }
            p.revents = 0;
        } while (poll(&p, 1, 0) > 0 && have < fsize * 8);
        if (eof && !prev_ok) break;
        if (prev_ok) {
            int black = 1;
            const uint8_t *picture = last;
            if (shades) {
                rotate_ms = colorize(last, rgb, held);
                memcpy(held, rgb, rsize);
                picture = rgb;
            }
            for (size_t i = 0; i < rsize && black; i++) black = picture[i] == 0;
            if (!sent) sent = calloc(1, rsize), ok = 0;
            if (black) {
                if (!ok || memcmp(sent, picture, rsize)) command_block(CMD_CLEAR, NULL, 0);
                ok = 1;
                memcpy(sent, picture, rsize);
            } else {
                int r = send_frame(picture, ok ? sent : NULL);
                if (r < 0) { fprintf(stderr, "ZeDMD lost\n"); return 3; }
                ok = r == 1;
                if (ok) memcpy(sent, picture, rsize);
            }
            prev_ok = NULL;
        }
        if (eof) break;
    }
    return 0;
}
