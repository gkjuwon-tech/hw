# Conet Tactile — host-mode simulator for the Wokwi test harness.
#
# Builds `scan_one_frame`, which reuses the firmware's `scanner_frame.h`
# (compress_sample + crc16_ccitt + frame_header_t) so the host harness
# exercises byte-for-byte the same protocol code that ships on silicon.

CXX      ?= g++
CXXFLAGS ?= -std=c++17 -O2 -Wall -Wextra -Wpedantic -Wno-c++17-extensions

HERE     := $(dir $(abspath $(lastword $(MAKEFILE_LIST))))
HDR      := $(HERE)../../scanner_frame.h

BIN      := scan_one_frame
SRC      := scan_one_frame.cpp

.PHONY: all clean

all: $(BIN)

$(BIN): $(SRC) $(HDR)
	$(CXX) $(CXXFLAGS) -o $@ $(SRC)

clean:
	rm -f $(BIN)
