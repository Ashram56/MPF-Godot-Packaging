// dmd_bridge: a game's DMD to a ZeDMD, PIN2DMD or Pixelcade with Serum colour, through PPUC's libdmdutil (libzedmd, libserum,
// PIN2DMD), used as it is: this program only reads frames and hands them over. Reads frames of width x height bytes from stdin,
// one byte a dot, the shade 0-15 (a DMD's 16 levels), and calls DMDUtil::DMD::UpdateData; the newest frame wins when frames
// arrive faster than the device takes them. Without a colourisation the shades scale --color; with one (--rom NAME --altcolor DIR:
// DIR/NAME/NAME.cRZ, .cROM or .cROMc) libserum colours the frames it knows and the others keep --color. Built by
// native/dmdutil/build.sh against the libraries native/dmdutil/build_dmdutil.sh makes.
//
//   dmd_bridge [--size WxH] [--color RRGGBB] [--rom NAME --altcolor DIR] [--device PORT] [--wifi ADDR]
//              [--brightness 0-15] [--rgb-out FILE] [--probe]
//   --probe: look for displays, say what was found, exit 0 (2: none)
//   --rgb-out FILE: also write the colourised RGB24 picture libdmdutil made to FILE after each frame (tests, no device needed)
// Exit when stdin closes. Messages on stderr.
#include <poll.h>
#include <unistd.h>

#include <chrono>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <string>
#include <thread>
#include <vector>

#include "DMDUtil/DMDUtil.h"

static void DMDUTILCALLBACK log_callback(DMDUtil_LogLevel level, const char* format, va_list args)
{
  if (level < DMDUtil_LogLevel_INFO) return;
  vfprintf(stderr, format, args);
  fputc('\n', stderr);
}

int main(int argc, char** argv)
{
  int width = 128, height = 32, brightness = -1;
  unsigned color = 0xff730d;
  std::string rom, altcolor, device, wifi, rgbOut;
  bool probe = false;
  for (int i = 1; i < argc; i++)
  {
    std::string a = argv[i];
    auto next = [&]() -> const char* { return i + 1 < argc ? argv[++i] : ""; };
    if (a == "--size") sscanf(next(), "%dx%d", &width, &height);
    else if (a == "--color") color = strtoul(next(), nullptr, 16);
    else if (a == "--rom") rom = next();
    else if (a == "--altcolor") altcolor = next();
    else if (a == "--device") device = next();
    else if (a == "--wifi") wifi = next();
    else if (a == "--brightness") brightness = atoi(next());
    else if (a == "--rgb-out") rgbOut = next();
    else if (a == "--probe") probe = true;
    else if (a == "--shades") continue;                // dmd_out adds it: the input is always shades
  }
  if (width <= 0 || height <= 0 || width * height > 256 * 64)
  {
    fprintf(stderr, "bad size %dx%d\n", width, height);
    return 1;
  }

  DMDUtil::Config* config = DMDUtil::Config::GetInstance();
  config->SetLogCallback(log_callback);
  config->SetZeDMD(true);
  if (!device.empty()) config->SetZeDMDDevice(device.c_str());
  if (!wifi.empty())
  {
    config->SetZeDMDWiFiEnabled(true);
    config->SetZeDMDWiFiAddr(wifi.c_str());
  }
  if (brightness >= 0) config->SetZeDMDBrightness(brightness);
  if (!rom.empty() && !altcolor.empty())
  {
    config->SetAltColor(true);
    config->SetAltColorPath(altcolor.c_str());
    config->SetShowNotColorizedFrames(true);          // frames Serum does not know are shown in --color
  }

  DMDUtil::DMD* dmd = new DMDUtil::DMD();
  if (!rom.empty() && !altcolor.empty())
  {
    dmd->SetAltColorPath(altcolor.c_str());
    dmd->SetRomName(rom.c_str());
  }
  DMDUtil::RGB24DMD* rgb24 = rgbOut.empty() ? nullptr : dmd->CreateRGB24DMD(width, height);
  dmd->FindDisplays();
  for (int i = 0; i < 100 && DMDUtil::DMD::IsFinding(); i++) std::this_thread::sleep_for(std::chrono::milliseconds(100));
  if (!dmd->HasDisplay() && !rgb24)
  {
    fprintf(stderr, "no ZeDMD or other display found\n");
    return 2;
  }
  fprintf(stderr, "display found%s\n", rom.empty() ? "" : (", colourisation " + rom + " in " + altcolor).c_str());
  if (probe) return 0;

  const size_t fsize = (size_t)width * height;
  std::vector<uint8_t> in(fsize * 8), last(fsize);
  size_t have = 0;
  const uint8_t r = color >> 16 & 255, g = color >> 8 & 255, b = color & 255;
  for (;;)
  {
    pollfd p = {0, POLLIN, 0};
    if (poll(&p, 1, 3000) == 0) continue;
    bool eof = false, got = false;
    do
    {
      ssize_t n = read(0, in.data() + have, in.size() - have);
      if (n <= 0)
      {
        eof = true;
        break;
      }
      have += n;
      size_t whole = have / fsize * fsize;
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
      dmd->UpdateData(last.data(), 4, (uint16_t)width, (uint16_t)height, r, g, b);
      if (rgb24)
      {
        std::this_thread::sleep_for(std::chrono::milliseconds(150));       // the output thread colours it
        const uint8_t* pic = rgb24->GetData();
        if (pic)
        {
          FILE* f = fopen(rgbOut.c_str(), "wb");
          if (f)
          {
            fwrite(pic, 1, fsize * 3, f);
            fclose(f);
          }
        }
      }
    }
    if (eof) break;
  }
  delete dmd;
  return 0;
}
