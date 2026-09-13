// RAM diagnostic only: floating-point formatted I/O is unsupported, never emulated.
// Match the newlib dispatch signatures in the pinned IDF newlib_init.c.
#include <stdio.h>
#include <stdarg.h>
#include <sys/reent.h>
#include <errno.h>

int __wrap__printf_float(struct _reent *r, void *data, FILE *stream,
        int (*write)(struct _reent *, FILE *, const char *, size_t), va_list *args) {
    (void)data; (void)stream; (void)write; (void)args;
    r->_errno=ENOTSUP;
    return -1;
}

int __wrap__scanf_float(struct _reent *r, void *data, FILE *stream, va_list *args) {
    (void)data; (void)stream; (void)args;
    r->_errno=ENOTSUP;
    return -1;
}
