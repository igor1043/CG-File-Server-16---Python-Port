#ifndef FIFA_COMPETITION_IDENTITY_H
#define FIFA_COMPETITION_IDENTITY_H
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

/* Object numbers are positions in CompData, not stable league identities. */
typedef struct { int id,type,parent; char name[64],display[160]; } CompIdentityNode;
typedef struct { unsigned short slot[65536]; unsigned count; CompIdentityNode nodes[8192]; } CompIdentityIndex;
static __inline int comp_identity_load(CompIdentityIndex *index,const char *path) {
    FILE *file=NULL;char line[512];memset(index,0,sizeof(*index));
    if(fopen_s(&file,path,"rb") || !file)return 0;
    while(fgets(line,sizeof(line),file)) {
        CompIdentityNode node;
        if(sscanf_s(line,"%d,%d,%63[^,],%159[^,],%d",&node.id,&node.type,
            node.name,(unsigned)sizeof(node.name),node.display,(unsigned)sizeof(node.display),&node.parent)!=5 ||
            node.id<0 || node.id>65535)continue;
        if(index->count>=8192 || index->slot[node.id]){fclose(file);memset(index,0,sizeof(*index));return 0;}
        index->nodes[index->count]=node;index->slot[node.id]=(unsigned short)(++index->count);
    }
    fclose(file);return index->count!=0;
}
static __inline const CompIdentityNode *comp_identity_node(const CompIdentityIndex *index,int id) {
    return id>=0 && id<=65535 && index->slot[id]?&index->nodes[index->slot[id]-1]:NULL;
}
static __inline const CompIdentityNode *comp_identity_root(const CompIdentityIndex *index,int id) {
    unsigned hop;const CompIdentityNode *node;
    for(hop=0;hop<64 && (node=comp_identity_node(index,id))!=NULL;++hop) {
        if(node->type==3)return node;
        id=node->parent;
    }
    return NULL;
}
static __inline int comp_identity_visual(const CompIdentityNode *node) {
    const char *prefix="TrophyName_Abbr15_",*text;int value;
    if(!node || node->type!=3)return 0;
    text=strstr(node->display,prefix);
    value=text?atoi(text+strlen(prefix)):node->name[0]=='C'?atoi(node->name+1):0;
    return value>0 && value<=65535?value:0;
}
static __inline int comp_identity_mapping(const CompIdentityIndex *index,const char *line,int *visual) {
    int hint=0,value=0,found=0;unsigned i;char name[64],display[160];const char *first=strchr(line,'|');
    if(first && strchr(first+1,'|')) {
        if(sscanf_s(line,"%d|%d|%63[^|]|%159[^\r\n]",&hint,&value,name,(unsigned)sizeof(name),display,(unsigned)sizeof(display))!=4)return 0;
        if(hint<=0 || hint>65535 || value<=0 || value>65535)return 0;
        for(i=0;i<index->count;++i) {
            const CompIdentityNode *node=&index->nodes[i];
            if(node->type==3 && !strcmp(node->name,name) && !strcmp(node->display,display)) {
                if(found)return 0;
                found=node->id;
            }
        }
    } else if(sscanf_s(line,"%d|%d",&hint,&value)==2) {
        const CompIdentityNode *node=comp_identity_node(index,hint);
        /* Legacy rows are safe only if the installed root agrees with the image ID. */
        if(value<=0 || value>65535 || comp_identity_visual(node)!=value)return 0;
        found=hint;
    }
    if(found)*visual=value;
    return found;
}
/* Translate a saved career's semantic visual identity to the installed
 * competition ID. Numeric object coincidences never choose artwork. */
static __inline int comp_identity_live_id(const CompIdentityIndex *index,int asset) {
    unsigned i;int found=0;
    if(asset<=0 || asset>65535)return 0;
    for(i=0;i<index->count;++i) {
        const CompIdentityNode *node=&index->nodes[i];
        if(node->type!=3 || comp_identity_visual(node)!=asset)continue;
        if(found && found!=node->id)return 0;
        found=node->id;
    }
    return found;
}
static __inline int comp_identity_key(const CompIdentityIndex *index,int id,char *out,size_t capacity) {
    const CompIdentityNode *chain[64],*node;unsigned count=0,i;size_t used=0;
    if(!capacity)return 0;out[0]=0;
    while(count<64 && (node=comp_identity_node(index,id))!=NULL) {
        unsigned other;
        for(other=0;other<index->count;++other) {
            const CompIdentityNode *candidate=&index->nodes[other];
            if(candidate->id!=node->id && candidate->type==node->type &&
               (node->type==3 || candidate->parent==node->parent) &&
               !strcmp(candidate->name,node->name) && !strcmp(candidate->display,node->display))return 0;
        }
        chain[count++]=node;if(node->type==3)break;id=node->parent;
    }
    if(!count || chain[count-1]->type!=3)return 0;
    for(i=count;i>0;--i) {
        int length;node=chain[i-1];
        if(strpbrk(node->name,"|~:") || strpbrk(node->display,"|~:"))return 0;
        length=snprintf(out+used,capacity-used,"%s%d:%s:%s",used?"~":"",node->type,node->name,node->display);
        if(length<0 || (size_t)length>=capacity-used){out[0]=0;return 0;}used+=(size_t)length;
    }
    return 1;
}
#endif
