#ifndef FIFA16_STADIUM_THUMBNAIL_H
#define FIFA16_STADIUM_THUMBNAIL_H
#include <stddef.h>
enum {
    STADIUM_IMAGE_MISSING = 0,
    STADIUM_IMAGE_CURRENT = 1,
    STADIUM_IMAGE_COPIED = 2,
    STADIUM_IMAGE_CONVERTED = 3
};
/* Copies valid DDSs or decodes a local image through Windows WIC. Originals
 * are read-only; converted DDSs preserve decoded dimensions/pixels/alpha. */
int stadium_thumbnail_sync(const char *source, const char *destination);
int stadium_thumbnail_valid_dds(const char *path);
/* Resolve an installed stadium's existing native movie by DB stadium ID. */
int stadium_thumbnail_native(const char *art_directory,int stadium,
    char *key,size_t capacity);
/* The native asset tile loads a movie, not a loose DDS. Generate its small
 * image_mc wrapper locally and return a content-addressed stadium helper key.
 * No original BIG or photo is overwritten. */
int stadium_thumbnail_package(const char *dds, const char *art_directory,
    char *key, size_t capacity);
#endif
