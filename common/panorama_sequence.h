#pragma once
namespace panorama {
// Shared ordering for the normal stadium panorama and the club visitor.
// Start with the exterior orbit, horizontal profile and halfway traverse.
inline constexpr unsigned sequenceShot(unsigned cursor,unsigned count){
 const unsigned position=cursor%count,priority=count-36;
 return position<priority?36+position:((position-priority)*5)%36;
}
}
