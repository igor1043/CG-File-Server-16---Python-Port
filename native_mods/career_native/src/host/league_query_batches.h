#ifndef FIFA_LEAGUE_QUERY_BATCHES_H
#define FIFA_LEAGUE_QUERY_BATCHES_H
#include <windows.h>
/* Bound the existing database query builder, preserving all club results. */
BOOL league_query_batches_start(const char *game_dir, const char *mod_dir);
#endif
