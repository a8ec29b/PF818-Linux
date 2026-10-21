#include <stdarg.h>
#include <stddef.h>
#include <stdio.h>
#include <string.h>
#include <sys/select.h>
int __android_log_print(int priority, const char *tag, const char *format, ...)
{
    return 0;
}
size_t __strlen_chk(const char *s, size_t limit) { return strlen(s); }
void __FD_SET_chk(int fd, fd_set *set, size_t size) { FD_SET(fd, set); }
int __FD_ISSET_chk(int fd, const fd_set *set, size_t size) { return FD_ISSET(fd, set); }
