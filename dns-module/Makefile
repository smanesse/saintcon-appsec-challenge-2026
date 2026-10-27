CC = gcc
CFLAGS = -g -O0 -std=c11 -fno-stack-protector -z execstack -no-pie -Wall -pthread

TARGET = dnsm

all: $(TARGET)

$(TARGET): dnsm.c
	$(CC) $(CFLAGS) -o $(TARGET) dnsm.c

clean:
	rm -f $(TARGET)

.PHONY: all clean
