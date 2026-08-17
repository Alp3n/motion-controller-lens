# Mostek SC4-Hub — buduje się przeciw sFoundation z vendor/teknic/.
#
#   make            zbuduj
#   make run        zbuduj i uruchom
#   make identify   zbuduj i uruchom identyfikację osi

SF   := ../vendor/teknic/Linux_Software/sFoundation
LIB  := $(abspath ../vendor/teknic/lib)

CXX      ?= g++
CXXFLAGS += -std=c++11 -O2 -Wall -I"$(SF)/inc/inc-pub"
LDFLAGS  += -L"$(LIB)" -Wl,-rpath="$(LIB)"
LDLIBS   += -lsFoundation20 -lpthread

TARGET := sc4hub_bridge

all: $(TARGET)

$(TARGET): sc4hub_bridge.cpp
	$(CXX) $(CXXFLAGS) -o $@ $< $(LDFLAGS) $(LDLIBS)

run: $(TARGET)
	./$(TARGET)

identify: $(TARGET)
	./$(TARGET) --identify

clean:
	rm -f $(TARGET)

.PHONY: all run identify clean
