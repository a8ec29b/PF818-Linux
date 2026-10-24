CC ?= cc
CFLAGS ?= -O2 -Wall -Wextra -Werror -std=c11
OUT ?= ../../build/round5/pf818-scan

.PHONY: all clean
all: $(OUT)

$(OUT): pf818-scan.c
	mkdir -p $(dir $(OUT))
	$(CC) $(CFLAGS) $(LDFLAGS) -o $@ $<

clean:
	rm -f $(OUT)
