/* SPDX-License-Identifier: MIT
 * PF818 decoded barcode reader. No Android or vendor library is required.
 */
#define _DEFAULT_SOURCE
#define _POSIX_C_SOURCE 200809L
#ifdef __APPLE__
#define _DARWIN_C_SOURCE
#endif
#include <errno.h>
#include <fcntl.h>
#include <limits.h>
#include <poll.h>
#include <signal.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/file.h>
#include <termios.h>
#include <time.h>
#include <unistd.h>

#define MAX_SCAN 65536
static volatile sig_atomic_t stopped;
static int once, json_output, hex_output, gap_only;

static void stop(int sig) { stopped = sig; }

static int64_t now_ms(void)
{
    struct timespec t;
    if (clock_gettime(CLOCK_MONOTONIC, &t)) { perror("clock_gettime"); exit(1); }
    return (int64_t)t.tv_sec * 1000 + t.tv_nsec / 1000000;
}

static int number(const char *s, int min, int max)
{
    char *end;
    errno = 0;
    long n = strtol(s, &end, 10);
    if (errno || !*s || *end || n < min || n > max) {
        fprintf(stderr, "Invalid numeric argument: %s\n", s); exit(1);
    }
    return (int)n;
}

static int utf8(const unsigned char *s, size_t n)
{
    size_t i = 0;
    while (i < n) {
        unsigned c = s[i++], need, value, minimum;
        if (c < 0x80) continue;
        if (c >= 0xc2 && c <= 0xdf) { need = 1; value = c & 31; minimum = 0x80; }
        else if (c >= 0xe0 && c <= 0xef) { need = 2; value = c & 15; minimum = 0x800; }
        else if (c >= 0xf0 && c <= 0xf4) { need = 3; value = c & 7; minimum = 0x10000; }
        else return 0;
        if (i + need > n) return 0;
        while (need--) {
            c = s[i++];
            if ((c & 0xc0) != 0x80) return 0;
            value = (value << 6) | (c & 63);
        }
        if (value < minimum || value > 0x10ffff || (value >= 0xd800 && value <= 0xdfff)) return 0;
    }
    return 1;
}

static void print_hex(const unsigned char *s, size_t n)
{
    for (size_t i = 0; i < n; i++) printf("%02x", s[i]);
}

static int emit(const unsigned char *s, size_t n)
{
    /* Observed at port open on this unit; factory app also ignores status frames. */
    static const unsigned char status[] = {0x00, 0x00, 0xff, 0xfc};
    if (!n || (n == sizeof(status) && !memcmp(s, status, n))) return 0;
    if (json_output) {
        fputs("{\"text\":", stdout);
        if (utf8(s, n)) {
            putchar('"');
            for (size_t i = 0; i < n; i++) {
                unsigned c = s[i];
                if (c == '"' || c == '\\') { putchar('\\'); putchar((int)c); }
                else if (c < 32 || c == 127) printf("\\u%04x", c);
                else putchar((int)c);
            }
            putchar('"');
        } else fputs("null", stdout);
        fputs(",\"hex\":\"", stdout); print_hex(s, n);
        printf("\",\"bytes\":%zu}\n", n);
    } else if (hex_output) { print_hex(s, n); putchar('\n'); }
    else { fwrite(s, 1, n, stdout); putchar('\n'); }
    if (fflush(stdout) || ferror(stdout)) { perror("stdout"); return -1; }
    return 1;
}

static void usage(FILE *f)
{
    fputs("Usage: pf818-scan [--device PATH] [--once] [--timeout SECONDS]\n"
          "                  [--json | --hex] [--framing auto|gap] [--gap-ms MS]\n"
          "Defaults: /dev/pf818-scanner, 115200 8N1, auto framing, 500 ms gap.\n"
          "auto: CR/LF delimiters, with idle-gap fallback for scanners without suffix.\n"
          "gap: preserve embedded CR/LF; use --json for multiline/binary QR payloads.\n"
          "--timeout limits the entire run; 0 (default) waits indefinitely.\n"
          "Exit: 0 success, 1 error, 2 timeout, 128+signal interrupted.\n", f);
}

int main(int argc, char **argv)
{
    const char *device = "/dev/pf818-scanner";
    int timeout = 0, gap = 500, fd = -1, configured = 0, result = 1;
    unsigned char buffer[MAX_SCAN];
    size_t used = 0;
    int64_t last_byte = 0, deadline;
    struct termios original, settings;
    for (int i = 1; i < argc; i++) {
        if (!strcmp(argv[i], "--help")) { usage(stdout); return 0; }
        else if (!strcmp(argv[i], "--once")) once = 1;
        else if (!strcmp(argv[i], "--json")) json_output = 1;
        else if (!strcmp(argv[i], "--hex")) hex_output = 1;
        else if ((!strcmp(argv[i], "--device") || !strcmp(argv[i], "--timeout") ||
                  !strcmp(argv[i], "--gap-ms") || !strcmp(argv[i], "--framing")) && i + 1 < argc) {
            const char *key = argv[i++], *value = argv[i];
            if (!strcmp(key, "--device")) device = value;
            else if (!strcmp(key, "--timeout")) timeout = number(value, 0, INT_MAX / 1000);
            else if (!strcmp(key, "--gap-ms")) gap = number(value, 1, 60000);
            else if (!strcmp(value, "gap")) gap_only = 1;
            else if (!strcmp(value, "auto")) gap_only = 0;
            else { usage(stderr); return 1; }
        } else { usage(stderr); return 1; }
    }
    if (json_output && hex_output) { usage(stderr); return 1; }
    signal(SIGINT, stop); signal(SIGTERM, stop); signal(SIGPIPE, stop);
    /* Read-only: never transmit scanner configuration or trigger commands. */
    fd = open(device, O_RDONLY | O_NOCTTY | O_NONBLOCK);
    if (fd < 0) { perror(device); return 1; }
    if (flock(fd, LOCK_EX | LOCK_NB)) {
        fprintf(stderr, "%s: cannot acquire reader lock: %s\n", device, strerror(errno)); goto done;
    }
    if (tcgetattr(fd, &original)) { perror("tcgetattr"); goto done; }
    settings = original;
    cfmakeraw(&settings);
    settings.c_cflag &= ~(CSIZE | PARENB | PARODD | CSTOPB | CRTSCTS);
    settings.c_cflag |= CS8 | CLOCAL | CREAD;
    settings.c_cc[VMIN] = 0; settings.c_cc[VTIME] = 0;
    if (cfsetispeed(&settings, B115200) || cfsetospeed(&settings, B115200) ||
        tcsetattr(fd, TCSANOW, &settings)) { perror("configure 115200 8N1"); goto done; }
    configured = 1;
    /* Drop bytes buffered before the baud rate was set (including stale scans). */
    if (tcflush(fd, TCIFLUSH)) { perror("flush stale input"); goto done; }
    deadline = timeout ? now_ms() + (int64_t)timeout * 1000 : INT64_MAX;
    while (!stopped) {
        int64_t now = now_ms();
        /* Emit only complete frames before timeout; a late partial frame is not a scan. */
        if (used && now - last_byte >= gap && last_byte + gap <= deadline) {
            int n = emit(buffer, used); used = 0;
            if (n < 0) goto done;
            if (n && once) { result = 0; goto done; }
        }
        if (now >= deadline) { result = 2; goto done; }
        int64_t wait = deadline - now;
        if (used && wait > last_byte + gap - now) wait = last_byte + gap - now;
        if (wait > 250) wait = 250;
        struct pollfd p = {fd, POLLIN, 0};
        int ready = poll(&p, 1, (int)wait);
        if (ready < 0) { if (errno == EINTR) continue; perror("poll"); goto done; }
        if (!ready) continue;
        if (p.revents & (POLLERR | POLLHUP | POLLNVAL)) {
            fprintf(stderr, "%s: serial device disconnected\n", device); goto done;
        }
        if (p.revents & POLLIN) {
            unsigned char chunk[4096];
            ssize_t count = read(fd, chunk, sizeof(chunk));
            if (count < 0) {
                if (errno == EAGAIN || errno == EINTR) continue;
                perror("read"); goto done;
            }
            for (ssize_t i = 0; i < count; i++) {
                unsigned char c = chunk[i];
                if (!gap_only && (c == '\r' || c == '\n')) {
                    int n = emit(buffer, used); used = 0;
                    if (n < 0) goto done;
                    if (n && once) { result = 0; goto done; }
                } else {
                    if (used == sizeof(buffer)) {
                        fprintf(stderr, "Scan exceeds %u bytes; refusing a truncated result\n", MAX_SCAN); goto done;
                    }
                    buffer[used++] = c;
                }
            }
            if (count) last_byte = now_ms();
        }
    }
    result = 128 + stopped;
done:
    if (configured && tcsetattr(fd, TCSANOW, &original) && result == 0) {
        perror("restore termios"); result = 1;
    }
    if (fd >= 0) close(fd);
    return result;
}
