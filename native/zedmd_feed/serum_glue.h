/* Serum colourisation for zedmd_feed (libserum, https://github.com/PPUC/libserum, GPL v2): the ROM's shades in, an RGB
 * picture out. Built only with -DWITH_SERUM (native/zedmd_feed/build.sh). */
#ifndef SERUM_GLUE_H
#define SERUM_GLUE_H
#include <stdint.h>
#ifdef __cplusplus
extern "C" {
#endif
/* Load DIR/ROM/ROM.cROMc. 1 = loaded (the file's frame size is then w x h), 0 = failed (message on stderr). */
int serum_open(const char *dir, const char *rom, int w, int h);
/* shades: w*h bytes 0-15; rgb: w*h*3 bytes written. Returns 1 coloured, 0 unknown to the file (rgb untouched), 2 the same
 * frame as before (rgb untouched). *rotate_ms: ms until serum_rotate must be called (0: no rotation). */
int serum_colorize(const uint8_t *shades, uint8_t *rgb, int *rotate_ms);
/* The next colour rotation of the current frame into rgb. *rotate_ms as above. */
void serum_rotate(uint8_t *rgb, int *rotate_ms);
#ifdef __cplusplus
}
#endif
#endif
