// Reproduces three jetson-ffmpeg (h264_nvmpi) problems on a Jetson AGX Orin, L4T R36.4.3 (JetPack 6.2):
//   flush  - decode, avcodec_flush_buffers(), seek to 0, decode again: the second decode never returns
//   close  - prints how long avcodec_free_context() takes (about 1 s per decoder)
//   crash  - decode 100 frames, free the codec mid-stream, open a new one; repeated: NVIDIA's decoder thread
//            sometimes segfaults in libnvmmlite_video.so (run it in a loop, about 1 run in 10 to 30 crashes)
//
// Build against an FFmpeg 7.1 tree patched by jetson-ffmpeg's ffpatch.sh and configured with --enable-nvmpi:
//   gcc -O1 -I$FF nvmpi_seek_close.c -o nvmpi_seek_close $FF/libavformat/libavformat.a \
//       $FF/libavcodec/libavcodec.a $FF/libswresample/libswresample.a $FF/libavutil/libavutil.a \
//       -L/usr/local/lib -L/usr/lib/aarch64-linux-gnu/nvidia $(grep -E '^EXTRALIBS[-_A-Za-z]*=' \
//       $FF/ffbuild/config.mak | cut -d= -f2- | tr '\n' ' ')
// Any H.264 mp4 works, e.g. NVIDIA's sample remuxed:
//   ffmpeg -i /usr/src/jetson_multimedia_api/data/Video/sample_outdoor_car_1080p_10fps.h264 -c copy car.mp4
//   ./nvmpi_seek_close car.mp4 flush
#include <libavformat/avformat.h>
#include <libavcodec/avcodec.h>
#include <stdio.h>
#include <string.h>
#include <time.h>

static double now_ms(void)
{
    struct timespec t;
    clock_gettime(CLOCK_MONOTONIC, &t);
    return t.tv_sec * 1e3 + t.tv_nsec / 1e6;
}

static AVCodecContext *open_codec(AVFormatContext *fc, int vs)
{
    const AVCodec *c = avcodec_find_decoder_by_name("h264_nvmpi");
    AVCodecContext *cc = avcodec_alloc_context3(c);
    avcodec_parameters_to_context(cc, fc->streams[vs]->codecpar);
    if (avcodec_open2(cc, c, NULL) < 0) {
        fprintf(stderr, "cannot open h264_nvmpi\n");
        exit(1);
    }
    return cc;
}

// decodes up to max frames from the current position; returns how many came out
static int decode(AVFormatContext *fc, AVCodecContext *cc, int vs, int max)
{
    AVPacket *p = av_packet_alloc();
    AVFrame *f = av_frame_alloc();
    int n = 0;
    while (n < max && av_read_frame(fc, p) >= 0) {
        if (p->stream_index == vs) {
            avcodec_send_packet(cc, p);
            while (avcodec_receive_frame(cc, f) == 0)
                n++;
        }
        av_packet_unref(p);
    }
    av_packet_free(&p);
    av_frame_free(&f);
    return n;
}

int main(int argc, char **argv)
{
    if (argc < 3) {
        fprintf(stderr, "usage: %s file.mp4 flush|close|crash\n", argv[0]);
        return 2;
    }
    AVFormatContext *fc = NULL;
    if (avformat_open_input(&fc, argv[1], NULL, NULL) < 0 || avformat_find_stream_info(fc, NULL) < 0)
        return 1;
    int vs = av_find_best_stream(fc, AVMEDIA_TYPE_VIDEO, -1, -1, NULL, 0);
    AVCodecContext *cc = open_codec(fc, vs);

    if (!strcmp(argv[2], "flush")) {
        for (int pass = 0; pass < 3; pass++) {
            printf("pass %d: %d frames\n", pass, decode(fc, cc, vs, 100));
            fflush(stdout);
            avcodec_flush_buffers(cc);   // pass 1 hangs in the next avcodec_send_packet()
            av_seek_frame(fc, vs, 0, AVSEEK_FLAG_BACKWARD);
        }
    } else if (!strcmp(argv[2], "close")) {
        for (int fed = 0; fed < 2; fed++) {
            if (fed)
                decode(fc, cc, vs, 30);
            double t = now_ms();
            avcodec_free_context(&cc);
            printf("close after %s: %.0f ms\n", fed ? "30 frames" : "no packet", now_ms() - t);
            av_seek_frame(fc, vs, 0, AVSEEK_FLAG_BACKWARD);
            cc = open_codec(fc, vs);
        }
    } else {
        for (int i = 0; i < 3; i++) {
            printf("decoder %d: %d frames, closing mid-stream\n", i, decode(fc, cc, vs, 100));
            fflush(stdout);
            avcodec_free_context(&cc);
            av_seek_frame(fc, vs, 0, AVSEEK_FLAG_BACKWARD);
            cc = open_codec(fc, vs);
        }
    }
    avcodec_free_context(&cc);
    avformat_close_input(&fc);
    puts("OK");
    return 0;
}
