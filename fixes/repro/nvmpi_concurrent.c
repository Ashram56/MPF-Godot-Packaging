// Several decoders at once (jetson-ffmpeg h264_nvmpi): N threads, each opens a decoder, decodes K to 2K frames, every
// other time flushes, then frees it, `iters` times. Prints each thread's progress every 2 s; a hang shows as a count
// that stops moving. Jetson AGX Orin, L4T R36.4.3: 4 of 6 runs of `./nvmpi_concurrent in.mp4 3 40 10` hung.
// Build like nvmpi_seek_close.c, plus -lpthread.
#include <libavformat/avformat.h>
#include <libavcodec/avcodec.h>
#include <pthread.h>
#include <stdio.h>
#include <stdlib.h>
#include <unistd.h>
static const char *path; static int iters, K; static volatile int done[16];
static void *worker(void *arg) {
  int id = (int)(long)arg;
  for (int it = 0; it < iters; it++) {
    AVFormatContext *fc = NULL; avformat_open_input(&fc, path, NULL, NULL); avformat_find_stream_info(fc, NULL);
    int vs = av_find_best_stream(fc, AVMEDIA_TYPE_VIDEO, -1, -1, NULL, 0);
    const AVCodec *c = avcodec_find_decoder_by_name("h264_nvmpi");
    AVCodecContext *cc = avcodec_alloc_context3(c); avcodec_parameters_to_context(cc, fc->streams[vs]->codecpar);
    avcodec_open2(cc, c, NULL);
    AVPacket *p = av_packet_alloc(); AVFrame *f = av_frame_alloc(); int n = 0, k = K + (rand() % K);
    while (n < k && av_read_frame(fc, p) >= 0) { if (p->stream_index == vs) { avcodec_send_packet(cc, p); while (avcodec_receive_frame(cc, f) == 0) n++; } av_packet_unref(p); }
    if (it % 2) { avcodec_flush_buffers(cc); av_seek_frame(fc, vs, 0, AVSEEK_FLAG_BACKWARD); }
    av_packet_free(&p); av_frame_free(&f); avcodec_free_context(&cc); avformat_close_input(&fc);
    done[id] = it + 1;
  }
  return NULL;
}
int main(int argc, char **argv) {
  path = argv[1]; int nt = atoi(argv[2]); iters = atoi(argv[3]); K = atoi(argv[4]);
  pthread_t t[16]; for (long i = 0; i < nt; i++) pthread_create(&t[i], NULL, worker, (void *)i);
  for (;;) { sleep(2); int all = 1; printf("progress:"); for (int i = 0; i < nt; i++) { printf(" %d", done[i]); if (done[i] < iters) all = 0; } printf("\n"); fflush(stdout); if (all) break; }
  for (int i = 0; i < nt; i++) pthread_join(t[i], NULL); puts("OK"); return 0; }
