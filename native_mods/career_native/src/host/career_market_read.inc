/* Market reads are executed only by the existing owner-thread UI pump.
 * No remote thread, saved DATA edit, database write, UI hook or provider
 * pointer is used. A complete scoped snapshot is published atomically. */
#define MARKET_READ_MAX 8192
static const char *market_offer_fields[]={"offerid","result","offeredfee","teamid","offerteamid","snipedteamid","playerid","exchangeplayerid","date","stage","iscputransfer","isloan","isloanbuy","issnipe"};
static const char *market_contract_fields[]={"offerid","teamid","offerteamid","playerid","date","completedate","iscputransfer"};
static const char *market_player_fields[]={"playerid","commonnameid","firstnameid","lastnameid","overallrating","potential","preferredposition1"};
typedef struct MarketReadRows { int count,columns; int *values; } MarketReadRows;

static int market_read_page(void)
{
    static const unsigned offsets[]={232,192,136,472};
    uintptr_t node=0;unsigned i;char page[96];
    if(!read_card_scope((uintptr_t)g_module_base+0x3809030,&node,8))return 0;
    for(i=0;i<4;++i)if(!node || !read_card_scope(node+offsets[i],&node,8))return 0;
    return node && read_card_scope(node,page,sizeof(page)) && memchr(page,0,sizeof(page))
        && (!strcmp(page,"game/screens/career/server16/TransferMarket") || !strcmp(page,"game/screens/career/server16/TransferMarketLoading"));
}

static int market_read_table(void *backend,const char *table,const char **fields,int columns,
    const char *where,int value,MarketReadRows *out)
{
    unsigned __int64 query[7]={0},result=0;
    int query_ready=0,result_ready=0,ok=0,i,j,count;
    memset(out,0,sizeof(*out));out->columns=columns;
    __try {
        __try {
            void (*execute)(void *,void *,void *)=(void (*)(void *,void *,void *))(*(void ***)backend)[1];
            native_name_db.query_init(query,1,table);query_ready=1;
            if(where)native_name_db.where_int(query,where,0,value);
            native_name_db.result_init(&result);result_ready=1;
            execute(backend,query,&result);count=native_name_db.count(&result);
            if(count<0 || count>MARKET_READ_MAX)__leave;
            out->values=(int *)calloc((size_t)(count?count:1)*columns,sizeof(int));
            if(!out->values)__leave;
            for(i=0;i<count;++i)for(j=0;j<columns;++j)
                out->values[i*columns+j]=native_name_db.integer(&result,i,fields[j]);
            out->count=count;ok=1;
        } __finally {
            if(result_ready)native_name_db.result_free(&result);
            if(query_ready)native_name_db.query_free(query);
        }
    } __except(EXCEPTION_EXECUTE_HANDLER) {ok=0;}
    if(!ok){free(out->values);memset(out,0,sizeof(*out));}
    return ok;
}

static int market_read_same_context(const CareerContextRead *captured,int club,int today)
{
    CareerContextRead now;uintptr_t contexts;int selected,parts[3];unsigned char *calendar;
    memcpy(&now,&Fifa16CareerContextRead,sizeof(now));
    if(now.sequence!=captured->sequence || now.sequence&1 || now.epoch!=captured->epoch
        || now.registry!=captured->registry || now.service!=captured->service
        || now.pid!=GetCurrentProcessId() || now.owner_thread!=GetCurrentThreadId()
        || now.epoch!=fce_runtime_context_epoch() || !is_readable_range((void *)now.service,32)
        || *(uintptr_t *)now.service!=now.vtable)return 0;
    selected=*(int *)(now.service+0x14);contexts=*(uintptr_t *)(now.service+0x18);
    if(selected<0 || selected>7 || !is_readable_range((void *)(contexts+selected*0x318),0x318)
        || *(int *)(contexts+selected*0x318+0x18c)!=1
        || *(int *)(contexts+selected*0x318+0x1a4)!=club)return 0;
    calendar=bank_mail_service(now.registry,0x44563f0,0x40);
    if(!calendar)return 0;memcpy(parts,calendar+0x34,12);
    return parts[2]*10000+parts[1]*100+parts[0]==today;
}

static int market_write_rows(FILE *file,const char *label,const MarketReadRows *rows)
{
    int i,j;
    for(i=0;i<rows->count;++i){
        fprintf(file,"%s=",label);
        for(j=0;j<rows->columns;++j)fprintf(file,"%s%d",j?",":"",rows->values[i*rows->columns+j]);
        fputc('\n',file);
    }
    return !ferror(file);
}

static void drain_market_read(void)
{
    static ULONGLONG next;
    static unsigned entry;static int inside;
    CareerContextRead captured;uintptr_t contexts,context;void *names,*backend;
    unsigned char *calendar;int selected,club,today,parts[3],i,j,player,count=0,ok=0;
    int seen[MARKET_READ_MAX];FILE *file=NULL;ULONGLONG tick;
    MarketReadRows offers={0},contracts={0},players={0},links={0};
    const char *link_fields[]={"playerid","teamid"};
    char path[MAX_PATH],temporary[MAX_PATH];
    if(!market_read_page()){next=0;inside=0;return;}
    if(!inside){++entry;inside=1;}
    tick=GetTickCount64();if(tick<next)return;next=tick+2000;
    memcpy(&captured,&Fifa16CareerContextRead,sizeof(captured));
    if(g_current_stats_provider_owner || !fce_runtime_is_stable()
        || captured.schema!=1 || captured.size!=sizeof(captured) || captured.sequence&1
        || captured.pid!=GetCurrentProcessId() || captured.owner_thread!=GetCurrentThreadId()
        || captured.epoch!=fce_runtime_context_epoch()
        || !is_readable_range((void *)captured.service,32)
        || *(uintptr_t *)captured.service!=captured.vtable
        || !native_name_db.query_init || !native_name_db.where_int || !native_name_db.result_init
        || !native_name_db.count || !native_name_db.integer || !native_name_db.result_free || !native_name_db.query_free)return;
    selected=*(int *)(captured.service+0x14);contexts=*(uintptr_t *)(captured.service+0x18);
    if(selected<0 || selected>7)return;
    context=contexts+selected*0x318;
    if(!is_readable_range((void *)context,0x318) || *(int *)(context+0x18c)!=1)return;
    club=*(int *)(context+0x1a4);if(club<=0 || club>2000000)return;
    calendar=bank_mail_service(captured.registry,0x44563f0,0x40);
    names=bank_mail_service(captured.registry,0x4456560,8);
    if(!calendar || !names)return;
    backend=*(void **)names;if(!is_readable_range(backend,16))return;
    memcpy(parts,calendar+0x34,12);today=parts[2]*10000+parts[1]*100+parts[0];
    if(!fce_date_valid(today))return;
    snprintf(path,sizeof(path),"%s\\runtime\\club_environment\\market\\live_market.tsv",g_mod_dir);
    snprintf(temporary,sizeof(temporary),"%s.new",path);
    __try {
        __try {
            if(!market_read_table(backend,"career_transferoffer",market_offer_fields,14,"result",32,&offers)
                || !market_read_table(backend,"career_precontract",market_contract_fields,7,NULL,0,&contracts))__leave;
            file=fopen(temporary,"wb");if(!file)__leave;
            fprintf(file,"schema=1\npid=%lu\nepoch=%lu\ncontext=%llx\nregistry=%llx\nclub=%d\ndate=%d\ncaptured_ms=%llu\nentry=%u\n",
                GetCurrentProcessId(),captured.epoch,(unsigned long long)context,(unsigned long long)captured.registry,club,today,(unsigned long long)tick,entry);
            if(!market_write_rows(file,"offer",&offers) || !market_write_rows(file,"precontract",&contracts))__leave;
            for(i=0;i<offers.count+contracts.count;++i){
                player=i<offers.count?offers.values[i*14+6]:contracts.values[(i-offers.count)*7+3];
                if(player<=0)continue;
                for(j=0;j<count && seen[j]!=player;++j){}
                if(j<count)continue;if(count==MARKET_READ_MAX)__leave;seen[count++]=player;
                if(!market_read_table(backend,"players",market_player_fields,7,"playerid",player,&players)
                    || !market_read_table(backend,"teamplayerlinks",link_fields,2,"playerid",player,&links))__leave;
                if(!market_write_rows(file,"player",&players) || !market_write_rows(file,"link",&links))__leave;
                free(players.values);memset(&players,0,sizeof(players));
                free(links.values);memset(&links,0,sizeof(links));
            }
            if(i!=offers.count+contracts.count || !market_read_same_context(&captured,club,today))__leave;
            fprintf(file,"complete=1\n");ok=!ferror(file);
        } __finally {
            if(file){if(fclose(file))ok=0;file=NULL;}
            free(offers.values);free(contracts.values);free(players.values);free(links.values);
        }
    } __except(EXCEPTION_EXECUTE_HANDLER) {ok=0;}
    if(ok)MoveFileExA(temporary,path,MOVEFILE_REPLACE_EXISTING|MOVEFILE_WRITE_THROUGH);
    else DeleteFileA(temporary);
}
