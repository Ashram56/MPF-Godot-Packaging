// hwcmp FILE: decodes FILE with the software h264 decoder and with the V4L2 Request hwaccel, frame by frame, and prints the frames whose
// colour differs (mean absolute difference of Y and of the interleaved UV plane, after both are NV12). Summary line at the end.
#include <libavformat/avformat.h>
#include <libavcodec/avcodec.h>
#include <libavutil/hwcontext.h>
#include <libavutil/imgutils.h>
#include <libswscale/swscale.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static enum AVPixelFormat get_fmt(AVCodecContext *c, const enum AVPixelFormat *p) {
    for (; *p != AV_PIX_FMT_NONE; p++) if (*p == AV_PIX_FMT_DRM_PRIME) return *p;
    return AV_PIX_FMT_NONE;
}
typedef struct { AVFormatContext *fc; AVCodecContext *cc; int vs; } Dec;
static int open_dec(Dec *d, const char *path, int hw, AVBufferRef *dev) {
    memset(d, 0, sizeof *d);
    if (avformat_open_input(&d->fc, path, NULL, NULL) < 0 || avformat_find_stream_info(d->fc, NULL) < 0) return -1;
    d->vs = av_find_best_stream(d->fc, AVMEDIA_TYPE_VIDEO, -1, -1, NULL, 0);
    if (d->vs < 0) return -1;
    const AVCodec *codec = avcodec_find_decoder(d->fc->streams[d->vs]->codecpar->codec_id);
    d->cc = avcodec_alloc_context3(codec);
    avcodec_parameters_to_context(d->cc, d->fc->streams[d->vs]->codecpar);
    if (hw) { d->cc->hw_device_ctx = av_buffer_ref(dev); d->cc->get_format = get_fmt; }
    else d->cc->thread_count = 1;
    return avcodec_open2(d->cc, codec, NULL);
}
// next decoded frame as NV12 in out (system memory); 0 ok, 1 eof
static int next(Dec *d, AVFrame *out, int hw) {
    AVPacket *pkt = av_packet_alloc(); AVFrame *f = av_frame_alloc();
    for (;;) {
        int r = avcodec_receive_frame(d->cc, f);
        if (r == 0) {
            av_frame_unref(out);
            if (hw) { if (av_hwframe_transfer_data(out, f, 0) < 0) { fprintf(stderr, "transfer failed\n"); exit(2); } }
            else {
                struct SwsContext *s = sws_getContext(f->width, f->height, f->format, f->width, f->height, AV_PIX_FMT_NV12, SWS_POINT, 0, 0, 0);
                out->format = AV_PIX_FMT_NV12; out->width = f->width; out->height = f->height; av_frame_get_buffer(out, 32);
                sws_scale(s, (const uint8_t * const *)f->data, f->linesize, 0, f->height, out->data, out->linesize); sws_freeContext(s);
            }
            av_frame_free(&f); av_packet_free(&pkt); return 0;
        }
        if (r == AVERROR_EOF) { av_frame_free(&f); av_packet_free(&pkt); return 1; }
        if (r != AVERROR(EAGAIN)) { av_frame_free(&f); av_packet_free(&pkt); return 1; }
        for (;;) {
            if (av_read_frame(d->fc, pkt) < 0) { avcodec_send_packet(d->cc, NULL); break; }
            if (pkt->stream_index == d->vs) { avcodec_send_packet(d->cc, pkt); av_packet_unref(pkt); break; }
            av_packet_unref(pkt);
        }
    }
}
static double mad(const uint8_t *a, int la, const uint8_t *b, int lb, int w, int h) {
    double s = 0; for (int y = 0; y < h; y++) for (int x = 0; x < w; x++) s += abs(a[y*la+x] - b[y*lb+x]);
    return s / (w * h);
}
int main(int argc, char **argv) {
    av_log_set_level(AV_LOG_ERROR);
    AVBufferRef *dev = NULL;
    if (av_hwdevice_ctx_create(&dev, AV_HWDEVICE_TYPE_V4L2REQUEST, NULL, NULL, 0) < 0) { fprintf(stderr, "no v4l2request device\n"); return 2; }
    Dec sw, hw;
    if (open_dec(&sw, argv[1], 0, NULL) < 0 || open_dec(&hw, argv[1], 1, dev) < 0) { fprintf(stderr, "open failed\n"); return 2; }
    AVFrame *a = av_frame_alloc(), *b = av_frame_alloc();
    int n = 0, bad = 0, first = -1, last = -1; double maxuv = 0;
    while (!next(&sw, a, 0) && !next(&hw, b, 1)) {
        double dy = mad(a->data[0], a->linesize[0], b->data[0], b->linesize[0], a->width, a->height);
        double duv = mad(a->data[1], a->linesize[1], b->data[1], b->linesize[1], a->width, a->height / 2);
        if (duv > maxuv) maxuv = duv;
        if (dy > 4 || duv > 4) { bad++; if (first < 0) first = n; last = n; if (bad <= 5) printf("  frame %d: dY=%.1f dUV=%.1f\n", n, dy, duv); }
        n++;
    }
    printf("%s: %d frames, %d differ (first %d, last %d), max dUV %.1f\n", argv[1], n, bad, first, last, maxuv);
    return 0;
}
