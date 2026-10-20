#pragma once
#include <cstddef>
struct SmokeMachineSite {float x,z,yaw;};
// Move the eight sideline bases 100cm outward from the previous 3750cm layout.
// Models and outlets share these coordinates; spare ball positions are independent.
static constexpr SmokeMachineSite machineSites[]={
    {-2800,-3850,0},{-2800,3850,3.14159265f},
    {-1400,-3850,0},{-1400,3850,3.14159265f},
    {1400,-3850,0},{1400,3850,3.14159265f},
    {2800,-3850,0},{2800,3850,3.14159265f},
    {-5900,-1800,1.57079633f},{5900,-1800,-1.57079633f},
    {-5900,1800,1.57079633f},{5900,1800,-1.57079633f},
    {-5900,-2100,1.57079633f},{5900,-2100,-1.57079633f},
    {-5900,-700,1.57079633f},{5900,-700,-1.57079633f},
    {-5900,700,1.57079633f},{5900,700,-1.57079633f},
    {-5900,2100,1.57079633f},{5900,2100,-1.57079633f}
};
static constexpr std::size_t machineCount=sizeof(machineSites)/sizeof(machineSites[0]);
static constexpr int pyroSidelineCount=8;
static constexpr int pyroIntroCount=(int)machineCount;
static constexpr int pyroGoalCount=pyroIntroCount-pyroSidelineCount;
static constexpr float machineOutletHeightCm=57.0f;
// Measured from the converted mesh's upper barrel ring (local Z ~=15cm).
static constexpr float machineOutletForwardCm=15.0f;
inline const SmokeMachineSite& pyro_site(bool goal,int index){
    return machineSites[(goal?pyroSidelineCount:0)+index];
}
