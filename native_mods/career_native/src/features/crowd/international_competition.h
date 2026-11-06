#ifndef FIFA16_CROWD_INTERNATIONAL_COMPETITION_H
#define FIFA16_CROWD_INTERNATIONAL_COMPETITION_H
#include "../../core/fce_model.h"

/* Use the club's next actual fixture, independent of the selected table/tab.
 * Domestic cups/leagues descend through a type-2 country. Continental cups
 * descend from a type-1 confederation or the type-0 FIFA world node.
 * Preseason descends through its own country node, so receives no bonus. */
static __inline const FceFixture *crowd_next_actual_fixture(
    const FceModel *model, int club)
{
    const FceFixture *best = NULL;
    size_t i;
    if (!model || !model->fixtures || club <= 0 || !fce_date_valid(model->date))
        return NULL;
    for (i = 0; i < model->fixture_count; ++i) {
        const FceFixture *fixture = model->fixtures + i;
        if (fixture->played_raw || fixture->home <= 0 || fixture->away <= 0
            || (fixture->home != club && fixture->away != club)
            || !fce_date_valid(fixture->date_raw) || fixture->date_raw < model->date)
            continue;
        if (!best || fixture->date_raw < best->date_raw
            || (fixture->date_raw == best->date_raw && fixture->time_raw < best->time_raw)
            || (fixture->date_raw == best->date_raw && fixture->time_raw == best->time_raw
                && fixture->id < best->id))
            best = fixture;
    }
    return best;
}

static __inline int crowd_fixture_is_international(
    const FceModel *model, const FceFixture *fixture)
{
    int root, parent = -1;
    size_t i;
    if (!model || !model->nodes || !fixture)
        return 0;
    root = fce_model_ancestor(model, fixture->competition_object, 3);
    if (root < 0)
        return 0;
    for (i = 0; i < model->node_count; ++i)
        if (model->nodes[i].id == root) {
            parent = model->nodes[i].parent;
            break;
        }
    for (i = 0; i < model->node_count; ++i)
        if (model->nodes[i].id == parent)
            return model->nodes[i].type == 1 || model->nodes[i].type == 0;
    return 0;
}
#endif
