#pragma once
#include <windows.h>
struct CrowdShared {
    volatile DWORD owner_pid, heartbeat, game_pid;
    volatile LONG generation, home_id, away_id, phase, requested_percent;
    volatile LONG command, ack, status, current_percent, automatic_percent;
};
void crowd_bridge_start(void (*logger)(const char *));
