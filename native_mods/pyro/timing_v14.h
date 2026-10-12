#pragma once
#include <stdint.h>
static bool pyro_show_expired(uint64_t now,uint64_t start,bool goal) {
    return now<start || now-start>=(goal?25000ULL:60000ULL);
}
