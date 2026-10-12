"""Directional focus follows the visible layout; Tab retains sequential order."""
def move_focus(current, kind, targets, preferred=None):
    rectangles=dict(targets)
    if current not in rectangles:return targets[0][0] if targets else current
    if kind==9:
        order=list(rectangles);return order[(order.index(current)+1)%len(order)]
    if kind not in (2,3,4,5):return current
    rect=rectangles[current];cx=(rect[0]+rect[2])/2;cy=(rect[1]+rect[3])/2
    candidates=[]
    for focus,other in targets:
        if focus==current:continue
        x=(other[0]+other[2])/2;y=(other[1]+other[3])/2
        horizontal=kind in (2,3)
        overlap=min(rect[3],other[3])>max(rect[1],other[1]) if horizontal else min(rect[2],other[2])>max(rect[0],other[0])
        distance=(cx-x if kind==2 else x-cx if kind==3 else cy-y if kind==4 else y-cy)
        if overlap and distance>0:
            sideways=abs(cy-y) if horizontal else abs(cx-x)
            candidates.append(((distance,sideways,focus!=preferred),focus))
    return min(candidates)[1] if candidates else current
