#include "teams.h"
#include "goals.h"
#include <assert.h>
#include <limits>
int main() {
    assert(pyro_team_valid(1043));assert(pyro_team_valid(113163));
    assert(pyro_team_valid(1));assert(pyro_team_valid(1000000));
    assert(!pyro_team_valid(0));assert(!pyro_team_valid(-1));assert(!pyro_team_valid(1000001));
    assert(!pyro_team_valid(1043.5));assert(!pyro_team_valid(std::numeric_limits<double>::quiet_NaN()));
    assert(!pyro_team_valid(std::numeric_limits<double>::infinity()));
    const uintptr_t sameTable=0x100000;
    assert(pyro_team_key(sameTable,1043,113163)!=pyro_team_key(sameTable,113163,1043));
    assert(pyro_team_key(sameTable,1,2)!=pyro_team_key(sameTable,3,4));
    PyroGoals g;
    assert(!g.update(100,0,0));
    assert(!g.update(200,1,0));assert(g.update(300,1,0));
    assert(!g.update(400,1,1));assert(!g.update(500,1,1));
    assert(!g.update(600,1,1));
    // Replay score rollback must not duplicate either team's goal.
    assert(!g.update(700,0,0));assert(!g.update(800,0,0));
    assert(!g.update(900,1,0));assert(!g.update(1000,1,0));
    assert(!g.update(1100,1,1));assert(!g.update(1200,1,1));
    assert(!g.update(1300,1,2));assert(!g.update(1400,1,2));
    assert(!g.update(1450,2,2));assert(g.update(1550,2,2));
    g=PyroGoals{};assert(!g.update(1500,0,0));
    assert(!g.update(1600,0,1));assert(!g.update(1700,0,1));
    assert(!g.update(1800,1,1));assert(g.update(1900,1,1));
    PyroGoals loadedScore;
    assert(!loadedScore.update(100,4,3));assert(!loadedScore.update(200,4,3));
    assert(!loadedScore.update(300,6,3));assert(!loadedScore.update(400,6,3));
}
