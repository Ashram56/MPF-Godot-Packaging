// dmd_bridge: a game's DMD to a ZeDMD, with Serum colour. The ZeDMD is driven by PPUC's libzedmd and the colour comes from
// PPUC's libserum, both used as they are (native/libzedmd/build_libzedmd.sh, native/serum/build_libserum.sh); this program
// only reads frames, calls libserum when a colourisation is given, and hands the picture to libzedmd.
//
// Reads frames of width x height bytes from stdin, one byte a dot, the shade 0-15 (a DMD's 16 levels). Without a colourisation
// the shades scale --color. With one (--serum-lib LIB --rom NAME --altcolor DIR: DIR/NAME/NAME.cRZ, .cROM or .cROMc) libserum
// colours the frames it knows (Serum v1 palette or v2 RGB565, 32p); the others keep --color; colour rotations run on libserum's
// timer. The newest frame wins when frames arrive faster than the ZeDMD takes them. Exit when stdin closes.
//
//   dmd_bridge [--size WxH] [--color RRGGBB] [--serum-lib LIB --rom NAME --altcolor DIR] [--device PORT] [--wifi ADDR]
//              [--brightness 0-15] [--rgb-out FILE] [--probe]
//   --probe: open the ZeDMD, say what it is, exit 0 (2: none found)
//   --rgb-out FILE: write each RGB888 picture to FILE as well, and do not need a ZeDMD (tests)
// "--shades" is accepted and ignored (the add-on dmd_out adds it). Messages on stderr.
#include <dlfcn.h>
#include <poll.h>
#include <signal.h>
#include <unistd.h>

#include <chrono>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <string>
#include <thread>
#include <vector>

#include "ZeDMD.h"

// the start of libserum's Serum_Frame_Struc (serum.h), up to nocolors
struct SerumFrame
{
  uint8_t *frame, *palette, *rotations;
  uint16_t* frame32;
  uint32_t width32;
  uint16_t *rotations32, *rotationsinframe32;
  uint8_t* modifiedelements32;
  uint16_t* frame64;
  uint32_t width64;
  uint16_t *rotations64, *rotationsinframe64;
  uint8_t* modifiedelements64;
  uint32_t SerumVersion;
  uint8_t flags;
  uint32_t nocolors;
};
static const uint8_t SERUM_FLAG_32P = 1;
static const uint32_t SERUM_NO_FRAME = 0xffffffffu, SERUM_SAME_FRAME = 0xfffffffeu;
static SerumFrame* (*serum_load)(const char*, const char*, uint8_t);
static uint32_t (*serum_colorize)(uint8_t*);
static uint32_t (*serum_rotate)();
static SerumFrame* serum;

static int width = 128, height = 32;
static uint8_t mono[16 * 3];

static void log_callback(const char* format, va_list args, const void*)
{
  vfprintf(stderr, format, args);
  fputc('\n', stderr);
}

static void mono_picture(const uint8_t* shades, uint8_t* rgb)
{
  for (int i = 0; i < width * height; i++) memcpy(rgb + i * 3, mono + (shades[i] & 15) * 3, 3);
}

// The picture libserum returned (v2 RGB565 32p, v1 palette). false: none.
static bool serum_picture(uint8_t* rgb)
{
  const int n = width * height;
  if (serum->SerumVersion >= 2)
  {
    if (!serum->frame32 || (int)serum->width32 != width) return false;
    for (int i = 0; i < n; i++)
    {
      const uint16_t c = serum->frame32[i];
      rgb[i * 3] = ((c >> 11) & 31) * 255 / 31;
      rgb[i * 3 + 1] = ((c >> 5) & 63) * 255 / 63;
      rgb[i * 3 + 2] = (c & 31) * 255 / 31;
    }
    return true;
  }
  if (!serum->frame || !serum->palette) return false;
  for (int i = 0; i < n; i++) memcpy(rgb + i * 3, serum->palette + serum->frame[i] * 3, 3);
  return true;
}

// Colour a frame of shades; returns libserum's rotation timer in ms (0: none).
static int colorize(const uint8_t* shades, uint8_t* rgb, const uint8_t* held)
{
  if (!serum)
  {
    mono_picture(shades, rgb);
    return 0;
  }
  static uint8_t in[256 * 64];
  const bool four = serum->nocolors == 4;
  for (int i = 0; i < width * height; i++) in[i] = four ? (shades[i] * 3 + 7) / 15 : shades[i];
  const uint32_t r = serum_colorize(in);
  if (r == SERUM_SAME_FRAME)
  {
    memcpy(rgb, held, (size_t)width * height * 3);
    return 0;
  }
  if (r == SERUM_NO_FRAME || !serum_picture(rgb))
  {
    mono_picture(shades, rgb);
    return 0;
  }
  return (int)(r & 0xffff);
}

static bool load_serum(const char* lib, const char* dir, const char* rom)
{
  void* h = dlopen(lib, RTLD_NOW | RTLD_LOCAL);
  if (!h)
  {
    fprintf(stderr, "serum: %s\n", dlerror());
    return false;
  }
  serum_load = (decltype(serum_load))dlsym(h, "Serum_Load");
  serum_colorize = (decltype(serum_colorize))dlsym(h, "Serum_Colorize");
  serum_rotate = (decltype(serum_rotate))dlsym(h, "Serum_Rotate");
  if (!serum_load || !serum_colorize || !serum_rotate)
  {
    fprintf(stderr, "serum: %s is not libserum\n", lib);
    return false;
  }
  serum = serum_load(dir, rom, SERUM_FLAG_32P);
  if (!serum)
  {
    fprintf(stderr, "serum: no colourisation %s in %s, single colour\n", rom, dir);
    return false;
  }
  fprintf(stderr, "serum: %s loaded (version %u, %u shades)\n", rom, serum->SerumVersion, serum->nocolors);
  return true;
}

int main(int argc, char** argv)
{
  signal(SIGPIPE, SIG_IGN);
  int brightness = -1;
  unsigned color = 0xff730d;
  std::string lib, rom, altcolor, device, wifi, rgbOut;
  bool probe = false;
  for (int i = 1; i < argc; i++)
  {
    const std::string a = argv[i];
    auto next = [&]() -> const char* { return i + 1 < argc ? argv[++i] : ""; };
    if (a == "--size") sscanf(next(), "%dx%d", &width, &height);
    else if (a == "--color") color = strtoul(next(), nullptr, 16);
    else if (a == "--serum-lib") lib = next();
    else if (a == "--rom") rom = next();
    else if (a == "--altcolor") altcolor = next();
    else if (a == "--device") device = next();
    else if (a == "--wifi") wifi = next();
    else if (a == "--brightness") brightness = atoi(next());
    else if (a == "--rgb-out") rgbOut = next();
    else if (a == "--probe") probe = true;
  }
  if (width <= 0 || height <= 0 || width % 8 || height % 4 || width * height > 256 * 64)
  {
    fprintf(stderr, "bad size %dx%d\n", width, height);
    return 1;
  }
  for (int n = 0; n < 16; n++)
  {
    mono[n * 3] = (color >> 16 & 255) * n / 15;
    mono[n * 3 + 1] = (color >> 8 & 255) * n / 15;
    mono[n * 3 + 2] = (color & 255) * n / 15;
  }
  if (!lib.empty() && !rom.empty() && !altcolor.empty()) load_serum(lib.c_str(), altcolor.c_str(), rom.c_str());

  ZeDMD* zedmd = nullptr;
  if (rgbOut.empty())
  {
    zedmd = new ZeDMD();
    zedmd->SetLogCallback(log_callback, nullptr);
    bool open;
    if (!wifi.empty()) open = zedmd->OpenWiFi(wifi.c_str());
    else
    {
      if (!device.empty()) zedmd->SetDevice(device.c_str());
      open = zedmd->Open();
    }
    if (!open)
    {
      fprintf(stderr, "no ZeDMD found\n");
      return 2;
    }
    zedmd->SetFrameSize(width, height);
    if (brightness >= 0) zedmd->SetBrightness(brightness > 15 ? 15 : brightness);
    fprintf(stderr, "ZeDMD %dx%d firmware %s\n", zedmd->GetWidth(), zedmd->GetHeight(), zedmd->GetFirmwareVersion());
    if (probe) return 0;
  }

  const size_t fsize = (size_t)width * height, rsize = fsize * 3;
  std::vector<uint8_t> in(fsize * 8), last(fsize), rgb(rsize), held(rsize, 0);
  size_t have = 0;
  int rotateMs = 0;
  auto show = [&]()
  {
    held = rgb;
    if (zedmd)
    {
      bool black = true;
      for (size_t i = 0; i < rsize && black; i++) black = rgb[i] == 0;
      if (black) zedmd->ClearScreen();
      else zedmd->RenderRgb888(rgb.data());
    }
    if (!rgbOut.empty())
    {
      FILE* f = fopen(rgbOut.c_str(), "wb");
      if (f)
      {
        fwrite(rgb.data(), 1, rsize, f);
        fclose(f);
      }
    }
  };
  for (;;)
  {
    pollfd p = {0, POLLIN, 0};
    const int idle = poll(&p, 1, rotateMs > 0 ? rotateMs : 3000);
    if (idle == 0 && rotateMs > 0 && serum)       // a colour rotation step: same frame, new colours
    {
      rotateMs = (int)(serum_rotate() & 0xffff);
      if (serum_picture(rgb.data())) show();
      continue;
    }
    if (idle == 0) continue;
    bool eof = false, got = false;
    do
    {
      const ssize_t n = read(0, in.data() + have, in.size() - have);
      if (n <= 0)
      {
        eof = true;
        break;
      }
      have += n;
      const size_t whole = have / fsize * fsize;
      if (whole)
      {
        memcpy(last.data(), in.data() + whole - fsize, fsize);
        memmove(in.data(), in.data() + whole, have - whole);
        have -= whole;
        got = true;
      }
      p.revents = 0;
    } while (poll(&p, 1, 0) > 0 && have < in.size());
    if (got)
    {
      rotateMs = colorize(last.data(), rgb.data(), held.data());
      show();
    }
    if (eof) break;
  }
  delete zedmd;
  return 0;
}
