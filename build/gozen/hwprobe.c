// hwprobe FILE OPENS [FRAMES] [EXTRA]: opens FILE OPENS times with the V4L2 Request hwaccel, decodes the first FRAMES frames each time
// (default 12) and compares them with the software decoder (decoded once). Per open: dY / dUV of the first frame, the worst frame, and,
// when the first frame is wrong, its mean signed difference and the mean |diff| of 8 horizontal and 8 vertical bands.
// EXTRA = extra_hw_frames (default 0).
#include <libavformat/avformat.h>
#include <libavcodec/avcodec.h>
#include <libavutil/hwcontext.h>
#include <libswscale/swscale.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static enum AVPixelFormat get_fmt(AVCodecContext *c, const enum AVPixelFormat *p) {
    for (; *p != AV_PIX_FMT_NONE; p++) if (*p == AV_PIX_FMT_DRM_PRIME) return *p;
    return AV_PIX_FMT_NONE;
}
typedef struct { AVFormatContext *fc; AVCodecContext *cc; int vs; } Dec;
static int open_dec(Dec *d, const char *path, int hw, AVBufferRef *dev, int extra) {
    memset(d, 0, sizeof *d);
    if (avformat_open_input(&d->fc, path, NULL, NULL) < 0 || avformat_find_stream_info(d->fc, NULL) < 0) return -1;
    d->vs = av_find_best_stream(d->fc, AVMEDIA_TYPE_VIDEO, -1, -1, NULL, 0);
    const AVCodec *codec = avcodec_find_decoder(d->fc->streams[d->vs]->codecpar->codec_id);
    d->cc = avcodec_alloc_context3(codec);
    avcodec_parameters_to_context(d->cc, d->fc->streams[d->vs]->codecpar);
    if (hw) { d->cc->hw_device_ctx = av_buffer_ref(dev); d->cc->get_format = get_fmt; d->cc->extra_hw_frames = extra; }
    else d->cc->thread_count = 1;
    return avcodec_open2(d->cc, codec, NULL);
}
static void close_dec(Dec *d) { avcodec_free_context(&d->cc); avformat_close_input(&d->fc); }
static int next(Dec *d, AVFrame *out, int hw) {
    AVPacket *pkt = av_packet_alloc(); AVFrame *f = av_frame_alloc();
    for (;;) {
        int r = avcodec_receive_frame(d->cc, f);
        if (r == 0) {
            av_frame_unref(out);
            if (hw) { if (av_hwframe_transfer_data(out, f, 0) < 0) exit(2); }
            else {
                struct SwsContext *s = sws_getContext(f->width, f->height, f->format, f->width, f->height, AV_PIX_FMT_NV12, SWS_POINT, 0, 0, 0);
                out->format = AV_PIX_FMT_NV12; out->width = f->width; out->height = f->height; av_frame_get_buffer(out, 32);
                sws_scale(s, (const uint8_t * const *)f->data, f->linesize, 0, f->height, out->data, out->linesize); sws_freeContext(s);
            }
            av_frame_free(&f); av_packet_free(&pkt); return 0;
        }
        if (r != AVERROR(EAGAIN)) { av_frame_free(&f); av_packet_free(&pkt); return 1; }
        for (;;) {
            if (av_read_frame(d->fc, pkt) < 0) { avcodec_send_packet(d->cc, NULL); break; }
            if (pkt->stream_index == d->vs) { avcodec_send_packet(d->cc, pkt); av_packet_unref(pkt); break; }
            av_packet_unref(pkt);
        }
    }
}
static double mad(const uint8_t *a, int la, const uint8_t *b, int lb, int x0, int x1, int y0, int y1, double *sgn) {
    double s = 0, g = 0; for (int y = y0; y < y1; y++) for (int x = x0; x < x1; x++) { int d = (int)b[y*lb+x] - a[y*la+x]; s += abs(d); g += d; }
    if (sgn) *sgn = g / ((x1-x0)*(y1-y0));
    return s / ((x1-x0)*(y1-y0));
}
int main(int argc, char **argv) {
    av_log_set_level(AV_LOG_ERROR);
    int opens = atoi(argv[2]), nf = argc > 3 ? atoi(argv[3]) : 12, extra = argc > 4 ? atoi(argv[4]) : 0;
    AVBufferRef *dev = NULL;
    if (av_hwdevice_ctx_create(&dev, AV_HWDEVICE_TYPE_V4L2REQUEST, NULL, NULL, 0) < 0) { fprintf(stderr, "no v4l2request device\n"); return 2; }
    AVFrame **ref = calloc(nf, sizeof *ref);
    Dec sw; open_dec(&sw, argv[1], 0, NULL, 0);
    int got = 0; for (; got < nf; got++) { ref[got] = av_frame_alloc(); if (next(&sw, ref[got], 0)) break; }
    nf = got; close_dec(&sw);
    int wrong = 0;
    for (int o = 0; o < opens; o++) {
        Dec hw; if (open_dec(&hw, argv[1], 1, dev, extra) < 0) { printf("open %d failed\n", o); continue; }
        AVFrame *b = av_frame_alloc(); double worst = 0, wuv = 0, y0 = 0, uv0 = 0; int worstf = -1;
        for (int i = 0; i < nf; i++) {
            if (next(&hw, b, 1)) break;
            double dy = mad(ref[i]->data[0], ref[i]->linesize[0], b->data[0], b->linesize[0], 0, b->width, 0, b->height, NULL);
            double duv = mad(ref[i]->data[1], ref[i]->linesize[1], b->data[1], b->linesize[1], 0, b->width, 0, b->height / 2, NULL);
            if (i == 0) { y0 = dy; uv0 = duv; }
            if (dy > worst) { worst = dy; worstf = i; }
            if (duv > wuv) wuv = duv;
            if (i == 0 && (dy > 2 || duv > 2)) {
                double sg; printf("  open %d frame0 bands rows:", o);
                for (int k = 0; k < 8; k++) printf(" %.0f", mad(ref[0]->data[0], ref[0]->linesize[0], b->data[0], b->linesize[0], 0, b->width, k*b->height/8, (k+1)*b->height/8, NULL));
                printf(" | cols:");
                for (int k = 0; k < 8; k++) printf(" %.0f", mad(ref[0]->data[0], ref[0]->linesize[0], b->data[0], b->linesize[0], k*b->width/8, (k+1)*b->width/8, 0, b->height, NULL));
                mad(ref[0]->data[0], ref[0]->linesize[0], b->data[0], b->linesize[0], 0, b->width, 0, b->height, &sg);
                double sgu; mad(ref[0]->data[1], ref[0]->linesize[1], b->data[1], b->linesize[1], 0, b->width, 0, b->height / 2, &sgu);
                printf(" | signed Y %.1f UV %.1f\n", sg, sgu);
            }
        }
        int bad = worst > 2 || wuv > 2; wrong += bad;
        printf("open %2d: frame0 dY %.1f dUV %.1f | worst dY %.1f (frame %d) dUV %.1f %s\n", o, y0, uv0, worst, worstf, wuv, bad ? "WRONG" : "ok");
        av_frame_free(&b); close_dec(&hw);
    }
    printf("%s: %d of %d opens wrong (frames %d, extra_hw_frames %d)\n", argv[1], wrong, opens, nf, extra);
    return 0;
}
