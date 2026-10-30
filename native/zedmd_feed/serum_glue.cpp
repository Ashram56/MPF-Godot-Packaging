/* Serum colourisation for zedmd_feed: see serum_glue.h. Licence: GPL v2 (it links libserum). */
#include "serum_glue.h"

#include <stdio.h>
#include <string.h>

#include "serum-decode.h"

static Serum_Frame_Struc *sf = NULL;
static int W = 128, H = 32;

/* RGB565 to RGB888 the way libserum's users do: each channel's top bits repeated into its low bits */
static void to_rgb(const uint16_t *src, uint8_t *rgb) {
    for (int i = 0; i < W * H; i++) {
        unsigned p = src[i], r = p >> 11 & 31, g = p >> 5 & 63, b = p & 31;
        rgb[i * 3] = r << 3 | r >> 2;
        rgb[i * 3 + 1] = g << 2 | g >> 4;
        rgb[i * 3 + 2] = b << 3 | b >> 2;
    }
}

static int plane(uint8_t *rgb) {
    if (sf->SerumVersion == SERUM_V2) {
        if (!(sf->flags & FLAG_RETURNED_32P_FRAME_OK) || !sf->frame32 || (int)sf->width32 != W) return 0;
        to_rgb(sf->frame32, rgb);
        return 1;
    }
    if (!sf->frame || !sf->palette) return 0;           /* v1: palette of 64 colours per frame */
    for (int i = 0; i < W * H; i++) memcpy(rgb + i * 3, sf->palette + sf->frame[i] * 3, 3);
    return 1;
}

int serum_open(const char *dir, const char *rom, int w, int h) {
    W = w;
    H = h;
    sf = Serum_Load(dir, rom, FLAG_REQUEST_32P_FRAMES);
    if (!sf) {
        fprintf(stderr, "Serum: %s/%s not loaded: %s\n", dir, rom, Serum_GetLastErrorMessage());
        return 0;
    }
    return 1;
}

int serum_colorize(const uint8_t *shades, uint8_t *rgb, int *rotate_ms) {
    uint8_t in[256 * 64];
    memcpy(in, shades, (size_t)W * H);
    uint32_t r = Serum_Colorize(in);
    *rotate_ms = 0;
    if (r == IDENTIFY_NO_FRAME) return 0;
    if (r == IDENTIFY_SAME_FRAME) return 2;
    *rotate_ms = r & 0xffff;
    return plane(rgb) ? 1 : 0;
}

void serum_rotate(uint8_t *rgb, int *rotate_ms) {
    uint32_t r = Serum_Rotate();
    *rotate_ms = r & 0xffff;
    plane(rgb);
}
