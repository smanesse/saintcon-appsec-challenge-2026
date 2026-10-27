CXX = g++
CXXFLAGS = -g -O0 -std=c++17 -fno-stack-protector -z execstack -no-pie -Wall -pthread

TARGET = fmm

all: $(TARGET) ftproot

$(TARGET): fmm.cpp
	$(CXX) $(CXXFLAGS) -o $(TARGET) fmm.cpp

ftproot:
	mkdir -p ftproot
	echo "This is a sample file students can RETR." > ftproot/welcome.txt

clean:
	rm -f $(TARGET) transfer.log

.PHONY: all clean
